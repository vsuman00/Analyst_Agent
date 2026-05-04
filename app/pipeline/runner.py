"""
run_full_pipeline.py — Master Orchestration Script
----------------------------------------------------
Executes the full deterministic 4-phase pipeline on a target repository
and outputs the finalized, validated Business Requirement Document (BRD).
"""

import sys
import json
import argparse
from pathlib import Path

# Phase 1: Context Extraction
from app.eca.repo_scanner import scan_repository
from app.eca.file_classifier import run_classifier
from app.eca.content_processor import run_content_processor
from app.context.aggregator import aggregate_context
from app.context.normalizer import normalize_context

# Phase 2 & 3: Analysis & Requirement Generation
from app.analysis.feature_extraction_agent import extract_features
from app.analysis.feature_validator import validate_features
from app.analysis.product_understanding_agent import understand_product
from app.analysis.functional_requirement_generator import generate_requirements
from app.analysis.non_functional_requirement_generator import generate_nfrs

# Phase 4: Composition & Validation
from app.analysis.brd_composer import compose_brd
from app.analysis.brd_fix_loop import run_fix_loop

# Phase 3.5: LLM Enrichment (optional — skipped gracefully if OPENAI_API_KEY not set)
def _try_enrich(val_feats_list, prod_dict):
    """
    Attempt LLM enrichment. Returns enriched features and updated business context.
    Silently skips if OPENAI_API_KEY is not configured.
    """
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        print("[LLM] OPENAI_API_KEY not set — skipping LLM enrichment.")
        return val_feats_list, prod_dict
    try:
        from app.utils.llm_enrichment import enrich_features, enrich_core_value
        enriched_feats = enrich_features(val_feats_list)
        core_value     = enrich_core_value(enriched_feats)
        prod_dict      = dict(prod_dict)
        prod_dict["core_value"] = core_value
        return enriched_feats, prod_dict
    except Exception as e:
        print(f"[LLM] Enrichment failed, continuing with deterministic output. Error: {e}")
        return val_feats_list, prod_dict


def log_stage(stage_num: str, name: str, status: str = "STARTED"):
    """Helper function to cleanly log pipeline stages."""
    if status == "STARTED":
        print(f"\n[{stage_num}/10] \033[94m{name} -> {status}...\033[0m")
    elif "SUCCESS" in status or "PASSED" in status:
        print(f"[{stage_num}/10] \033[92m{name} -> {status}\033[0m")
    else:
        print(f"[{stage_num}/10] \033[91m{name} -> {status}\033[0m")

def run_end_to_end(repo_url: str, output_dir: str):
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    dest_repo_dir = out_path / "runner_repo"

    print("\n==================================================")
    print(f"🚀 INITIATING DETERMINISTIC BRD PIPELINE")
    print(f"📦 Target: {repo_url}")
    print("==================================================")

    try:
        # ─── PHASE 1: CONTEXT EXTRACTION ─────────────────────────────────────
        log_stage("1", "RepoScanner")
        scan_data = scan_repository(repo_url, str(dest_repo_dir), skip_clone=True)
        if "error" in scan_data:
            raise RuntimeError(f"RepoScanner failed: {scan_data['error']}")
        log_stage("1", "RepoScanner", f"SUCCESS (Found {len(scan_data.get('files', []))} files)")

        log_stage("2", "FileClassifier")
        classified_data = run_classifier(scan_data)
        log_stage("2", "FileClassifier", "SUCCESS")

        log_stage("3", "ContentProcessor")
        chunks_data = run_content_processor(classified_data, dest_repo_dir)
        log_stage("3", "ContentProcessor", f"SUCCESS (Generated {len(chunks_data.get('chunks', []))} chunks)")

        log_stage("4", "ContextAggregator & Normalizer")
        aggregated_data = aggregate_context(chunks_data)
        normalized_data = normalize_context(aggregated_data)
        norm_modules = normalized_data.get("normalized_modules", [])
        log_stage("4", "ContextAggregator", f"SUCCESS ({len(norm_modules)} modules)")

        # ─── PHASE 2: ANALYSIS & FEATURE EXTRACTION ─────────────────────────
        log_stage("5", "FeatureExtractionAgent")
        chunks_list = chunks_data.get("chunks", [])
        feat_ext_result = extract_features(norm_modules, chunks_list)
        raw_feats = feat_ext_result.model_dump()
        log_stage("5", "FeatureExtractionAgent", f"SUCCESS ({len(raw_feats['features'])} raw features)")

        log_stage("6", "FeatureValidator")
        feat_val_result = validate_features(raw_feats["features"])
        val_feats = feat_val_result.model_dump()
        log_stage("6", "FeatureValidator", f"SUCCESS ({len(val_feats['validated_features'])} validated features)")

        log_stage("7", "ProductUnderstandingAgent")
        prod_result = understand_product(val_feats["validated_features"])
        prod_dict = prod_result.model_dump()
        log_stage("7", "ProductUnderstandingAgent", f"SUCCESS (Archetype: {prod_dict['product']['name']})")

        # ─── PHASE 3: REQUIREMENT GENERATION ─────────────────────────────────
        log_stage("8", "FunctionalRequirementGenerator")
        fr_result = generate_requirements(val_feats["validated_features"])
        fr_dict = fr_result.model_dump()
        log_stage("8", "FunctionalRequirementGenerator", f"SUCCESS ({len(fr_dict['functional_requirements'])} FRs)")

        log_stage("9", "NonFunctionalRequirementGenerator")
        system_type = prod_dict['product']['name']
        # Try to extract tech stack from chunks if possible, or just pass empty list for now
        nfr_result = generate_nfrs(system_type=system_type, tech_stack=[])
        nfr_dict = nfr_result.model_dump()
        log_stage("9", "NonFunctionalRequirementGenerator", f"SUCCESS ({len(nfr_dict['non_functional_requirements'])} NFRs)")

        # ─── PHASE 3.5: LLM ENRICHMENT ───────────────────────────────────
        enriched_feat_list, prod_dict = _try_enrich(
            val_feats["validated_features"], prod_dict
        )
        val_feats["validated_features"] = enriched_feat_list

        # ─── PHASE 4: COMPOSITION & VALIDATION ───────────────────────────────
        log_stage("10", "BRDComposer & FixLoop")
        initial_markdown = compose_brd(
            product_data=prod_dict,
            features_data=val_feats,
            fr_data=fr_dict,
            nfr_data=nfr_dict
        )
        
        loop_result = run_fix_loop(initial_markdown, max_iterations=2)
        final_markdown = loop_result["final_markdown"]
        final_val = loop_result["final_validation"]
        
        score = final_val["score"]
        status = "PASSED" if score >= 0.85 else "FAILED"
        log_stage("10", "BRDComposer & FixLoop", f"SUCCESS ({status} with score {score:.2f})")

        if final_val["issues"]:
            print("⚠️ Remaining Issues:")
            for issue in final_val["issues"]:
                print(f"   - {issue}")

        # ─── OUTPUT ─────────────────────────────────────────────────────────
        brd_out_path = out_path / "Target_BRD.md"
        with open(brd_out_path, "w", encoding="utf-8") as f:
            f.write(final_markdown)

        print("\n==================================================")
        print("✅ BRD PIPELINE COMPLETED SUCCESSFULLY")
        print(f"📄 Output saved to: {brd_out_path}")
        print("==================================================\n")

    except Exception as e:
        import traceback
        print("\n==================================================")
        print("❌ PIPELINE FAILED")
        traceback.print_exc()
        print("==================================================\n")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the full Analyst-Agent pipeline to generate a BRD.")
    parser.add_argument("repo_url", help="URL of the target GitHub repository")
    parser.add_argument("--outdir", default="runtime/pipeline_out", help="Directory to store outputs")
    args = parser.parse_args()

    run_end_to_end(args.repo_url, args.outdir)

def run_pipeline(repo_url: str, output_path: str = None) -> dict:
    from app.eca.repo_scanner import scan_repository
    from app.eca.file_classifier import run_classifier
    from app.eca.content_processor import run_content_processor
    from app.context.aggregator import aggregate_context
    from app.context.normalizer import normalize_context
    from app.context.validator import validate_context
    from app.output.final_output_builder import build_final_output
    from pathlib import Path

    out_dir = output_path if output_path else "runtime/pipeline_out"
    out_path_obj = Path(out_dir)
    out_path_obj.mkdir(parents=True, exist_ok=True)
    dest_repo_dir = out_path_obj / "runner_repo"

    scan_data = scan_repository(repo_url, str(dest_repo_dir), skip_clone=False)
    if "error" in scan_data:
        raise RuntimeError(f"RepoScanner failed: {scan_data['error']}")

    classified_data = run_classifier(scan_data)
    chunks_data = run_content_processor(classified_data, dest_repo_dir)

    aggregated_data = aggregate_context(chunks_data)
    normalized_data = normalize_context(aggregated_data)

    validation_data = validate_context(normalized_data)

    final_payload = build_final_output(
        scan_data,
        classified_data,
        chunks_data,
        normalized_data,
        validation_data
    )
    return final_payload
