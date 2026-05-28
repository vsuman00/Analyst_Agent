"""
run_full_pipeline.py — Master Orchestration Script
----------------------------------------------------
Executes the full deterministic 4-phase pipeline on a target repository
and outputs the finalized, validated Business Requirement Document (BRD).

Pipeline stages:
  1    RepoScanner
  2    FileClassifier
  3    ContentProcessor
  3.5  RepoContextBuilder
  3.6  RepoEvidenceManifest
  4    ContextAggregator & Normalizer
  4.5  SkillPackMatcher          ← NEW: dynamic skill pack detection
  4.7  SkillPackExecutor         ← NEW: run activated skill scripts
  5    FeatureExtractionAgent
  6    FeatureValidator
  6.5  Semantic Feature Pruning
  7    ProductUnderstandingAgent
  8    FunctionalRequirementGenerator
  9    NonFunctionalRequirementGenerator
  3.5L LLM Enrichment
  3.6L BusinessUnderstandingAgent
  3.7  BRD Deep Enrichment
  10   BRDComposer & FixLoop
"""

import sys
import json
import argparse
from pathlib import Path

# Prevent UnicodeEncodeError on Windows command consoles when printing emojis
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Phase 1: Context Extraction
from app.eca.repo_scanner import scan_repository
from app.eca.file_classifier import run_classifier
from app.eca.content_processor import run_content_processor
from app.eca.repo_context_builder import build_repo_context
from app.eca.api_extractor import extract_api_endpoints
from app.eca.dependency_extractor import extract_dependencies
from app.eca.evidence_manifest import build_evidence_manifest
from app.eca.entity_extractor import extract_entities
from app.context.aggregator import aggregate_context
from app.context.normalizer import normalize_context

# Phase 2 & 3: Analysis & Requirement Generation
from app.analysis.feature_extraction_agent import extract_features
from app.analysis.feature_validator import validate_features
from app.analysis.product_understanding_agent import understand_product
from app.analysis.business_understanding_agent import understand_business
from app.analysis.functional_requirement_generator import generate_requirements
from app.analysis.non_functional_requirement_generator import generate_nfrs

# Phase 4: Composition & Validation
from app.analysis.brd_composer import compose_brd
from app.analysis.brd_fix_loop import run_fix_loop

# Phase 3.5: LLM Enrichment (optional — skipped gracefully if OPENAI_API_KEY not set)
def _try_enrich(val_feats_list, prod_dict, tech_stack, evidence):
    """
    Attempt LLM enrichment. Returns enriched features, updated business context, and artifacts.
    Silently skips if OPENAI_API_KEY is not configured.
    """
    import os
    # Ensure .env is loaded — needed when running via CLI (run_end_to_end)
    # or if main.py's load_dotenv hasn't run yet.
    try:
        from dotenv import load_dotenv
        _env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        load_dotenv(dotenv_path=_env_path, override=False)
    except ImportError:
        pass

    if not os.environ.get("OPENAI_API_KEY"):
        print("[LLM] OPENAI_API_KEY not set — skipping LLM enrichment.")
        return val_feats_list, prod_dict, {}
    try:
        from app.utils.llm_enrichment import enrich_features, enrich_core_value, enrich_enterprise_artifacts
        enriched_feats = enrich_features(val_feats_list)
        core_value     = enrich_core_value(enriched_feats)
        prod_dict      = dict(prod_dict)
        prod_dict["core_value"] = core_value
        
        artifacts = enrich_enterprise_artifacts(
            business_context={"product_type": prod_dict["product"]["name"]},
            features=enriched_feats,
            tech_stack=tech_stack,
            evidence=evidence
        )
        return enriched_feats, prod_dict, artifacts
    except Exception as e:
        print(f"[LLM] Enrichment failed, continuing with deterministic output. Error: {e}")
        return val_feats_list, prod_dict, {}


def _build_tech_labels(dep_data: dict, evidence: dict) -> list:
    """Return a flat list of human-readable tech label strings.

    This is the single source of truth for the tech_stack value that flows
    into business_context and then into every BRD section composer.

    Generic by design \u2014 it reads what dependency_extractor and
    evidence_manifest already found.  No language-specific patterns here.

    Parameters
    ----------
    dep_data : output of extract_dependencies()
    evidence : output of build_evidence_manifest()

    Returns
    -------
    List[str] e.g. ["Kotlin", "Gradle", "Android", "Docker"]
    """
    labels: list = []
    seen: set = set()

    def _add(label: str) -> None:
        clean = label.strip()
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            labels.append(clean)

    # 1. Primary language \u2014 most important, always first
    lang = dep_data.get("language", "")
    if lang and lang != "unknown":
        _add(lang.title())

    # 2. Build tool
    build_tool = dep_data.get("build_tool", "")
    if build_tool and build_tool != "unknown":
        _add(build_tool.title())

    # 3. Deployment platform (android, ios, web, server, desktop)
    platform = evidence.get("platform", "")
    if platform and platform not in ("unknown", "library"):
        _add(platform.title())

    # 4. Infrastructure signals
    if evidence.get("has_docker"):
        _add("Docker")
    if evidence.get("has_kubernetes"):
        _add("Kubernetes")

    # 5. Top framework / library deps (generic \u2014 use names from build files)
    skip_cats  = {"testing", "build"}
    skip_names = {"jvm-target", "application", "android", "serialization"}
    dep_count = 0
    for dep in dep_data.get("dependencies", []):
        if dep_count >= 8:
            break
        cat  = dep.get("category", "")
        name = dep.get("name", "").strip()
        if cat in skip_cats:
            continue
        # Strip Maven/Gradle group prefix for display
        display = name.split(":")[-1].strip() if ":" in name else name
        display = display.strip().strip("\"' ")
        if not display or display.lower() in skip_names:
            continue
        _add(display)
        dep_count += 1

    return labels


def log_stage(stage_num: str, name: str, status: str = "STARTED"):
    """Helper function to cleanly log pipeline stages."""
    if status == "STARTED":
        print(f"\n[{stage_num}] \033[94m{name} -> {status}...\033[0m")
    elif "SUCCESS" in status or "PASSED" in status:
        print(f"[{stage_num}] \033[92m{name} -> {status}\033[0m")
    else:
        print(f"[{stage_num}] \033[91m{name} -> {status}\033[0m")

def run_full_pipeline_service(repo_url: str, output_dir: str) -> dict:
    """
    Executes the full 10-stage end-to-end pipeline (Phase 1 through 4) and returns
    a dictionary containing all generated contexts, features, requirements, and the finalized BRD.
    """
    from app.context.validator import validate_context
    from app.output.final_output_builder import build_final_output

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Derive a repo-specific clone directory so each repo is isolated
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")

    # ── Per-repo directory layout ──────────────────────────────────────────
    #   pipeline_out/{repo_name}/brd/      ← BRD .md / .docx
    #   pipeline_out/{repo_name}/debug/    ← all intermediate JSON dumps
    #   pipeline_out/{repo_name}/repo/src/ ← cloned source code
    repo_out_path  = out_path / repo_name
    brd_path       = repo_out_path / "brd"
    debug_path     = repo_out_path / "debug"
    dest_repo_dir  = repo_out_path / "repo" / "src"
    for _d in (brd_path, debug_path, dest_repo_dir):
        _d.mkdir(parents=True, exist_ok=True)

    print("\n==================================================")
    print(f"🚀 INITIATING DETERMINISTIC BRD PIPELINE")
    print(f"📦 Target: {repo_url}")
    print(f"📁 Output Dir: {repo_out_path}")
    print("==================================================")

    # ─── PHASE 1: CONTEXT EXTRACTION ─────────────────────────────────────
    log_stage("1", "RepoScanner")
    # skip_clone=False ensures we always clone the repo fresh
    scan_data = scan_repository(repo_url, str(dest_repo_dir), skip_clone=False)
    if "error" in scan_data:
        raise RuntimeError(f"RepoScanner failed: {scan_data['error']}")
    log_stage("1", "RepoScanner", f"SUCCESS (Found {len(scan_data.get('files', []))} files)")

    # ── DEBUG: Save scan_data (Stage 1 output) to JSON ────────────────────
    _scan_debug_path = debug_path / "scan_data.json"
    with open(_scan_debug_path, "w", encoding="utf-8") as _f:
        json.dump(scan_data, _f, indent=2, default=str)
    print(f"[DEBUG] scan_data saved → {_scan_debug_path}")

    log_stage("2", "FileClassifier")
    classified_data = run_classifier(scan_data)
    log_stage("2", "FileClassifier", "SUCCESS")

    # ── DEBUG: Save classified_data (Stage 2 output) to JSON ───────────────
    _classified_debug_path = debug_path / "classified_data.json"
    with open(_classified_debug_path, "w", encoding="utf-8") as _f:
        json.dump(classified_data, _f, indent=2, default=str)
    print(f"[DEBUG] classified_data saved → {_classified_debug_path}")

    log_stage("3", "ContentProcessor")
    chunks_data = run_content_processor(classified_data, dest_repo_dir)
    log_stage("3", "ContentProcessor", f"SUCCESS (Generated {len(chunks_data.get('chunks', []))} chunks)")

    # ── DEBUG: Save raw chunk data for inspection ──────────────────────
    _chunk_debug_path = debug_path / "ChunkData.json"
    with open(_chunk_debug_path, "w", encoding="utf-8") as _f:
        json.dump(chunks_data, _f, indent=2, default=str)
    print(f"[DEBUG] Chunk data saved → {_chunk_debug_path}")

    # ─── PHASE 1.5: EXTRACT DEPS & API BEFORE BUILDING REPO CONTEXT ──────
    # These must run FIRST so build_repo_context() receives accurate dep_data
    # and evidence — enabling evidence-driven tech_stack for all project types.
    log_stage("3.6", "DependencyExtractor + APIExtractor + EntityExtractor")
    api_data  = extract_api_endpoints(dest_repo_dir)
    dep_data  = extract_dependencies(dest_repo_dir)
    entity_data = extract_entities(dest_repo_dir)
    evidence  = build_evidence_manifest(dest_repo_dir, api_data, dep_data)
    log_stage("3.6", "RepoEvidenceManifest",
              f"SUCCESS (platform={evidence['platform']}, "
              f"lang={evidence['primary_language']}, "
              f"build={evidence['build_tool']}, "
              f"http_api={evidence['has_http_api']}, "
              f"android={evidence['has_android']}, "
              f"docker={evidence['has_docker']}, k8s={evidence['has_kubernetes']})")

    # ─── PHASE 1.5: BUILD RICH REPO CONTEXT ──────────────────────────────
    # Now pass dep_data + evidence so tech_stack is accurate from the start.
    log_stage("3.5", "RepoContextBuilder")
    repo_context = build_repo_context(
        str(dest_repo_dir), chunks_data,
        dep_data=dep_data,
        evidence=evidence,
    )
    repo_context["data_entities"] = entity_data.get("entities", [])
    log_stage("3.5", "RepoContextBuilder",
              f"SUCCESS (README: {repo_context['intent_signals'].get('source', 'none')}, "
              f"no_readme={repo_context['no_readme']})")

    # ── DEBUG: Save the two primary LLM inputs produced after ECA ──────────
    # repo_context  → used by FeatureExtractionAgent, ProductUnderstandingAgent,
    #                  BRDEnrichmentAgent as the main grounding document
    # evidence      → used by BRDComposer & grounding validator
    for _fname, _data in [
        ("repo_context.json", repo_context),
        ("evidence.json",     evidence),
    ]:
        _fpath = debug_path / _fname
        with open(_fpath, "w", encoding="utf-8") as _f:
            json.dump(_data, _f, indent=2, default=str)
        print(f"[DEBUG] Saved → {_fpath}")


    log_stage("4", "ContextAggregator & Normalizer")
    aggregated_data = aggregate_context(chunks_data)
    normalized_data = normalize_context(aggregated_data)
    norm_modules = normalized_data.get("normalized_modules", [])
    log_stage("4", "ContextAggregator", f"SUCCESS ({len(norm_modules)} modules)")

    # ── DEBUG: Save aggregated & normalized context to JSON ────────────────
    for _fname, _data in [
        ("aggregated_data.json", aggregated_data),
        ("normalized_data.json", normalized_data),
    ]:
        _fpath = debug_path / _fname
        with open(_fpath, "w", encoding="utf-8") as _f:
            json.dump(_data, _f, indent=2, default=str)
        print(f"[DEBUG] Saved → {_fpath}")

    # ─── STAGE 4.5: DYNAMIC SKILL PACK DETECTION ────────────────────────
    # Score all available skill packs (SKILL.md files) against repo evidence.
    # If no pack matches → SkillComposer auto-generates one via LLM.
    # This stage NEVER blocks the pipeline — failures fall through gracefully.
    skill_results = None
    try:
        from app.skills.skill_matcher import detect_skill_packs as _detect_skills
        from app.skills.skill_executor import execute_skill_packs as _exec_skills
        from app.schemas.models import SkillExecutionResult

        log_stage("4.5", "SkillPackMatcher")
        activated_packs = _detect_skills(evidence, repo_context, dep_data)
        if activated_packs:
            pack_summary = ", ".join(f"{s.name}({sc:.2f})" for s, sc in activated_packs)
            log_stage("4.5", "SkillPackMatcher", f"SUCCESS ({len(activated_packs)} packs: {pack_summary})")

            # ─── STAGE 4.7: SKILL PACK EXECUTION ────────────────────────
            log_stage("4.7", "SkillPackExecutor")
            skill_results = _exec_skills(activated_packs, str(dest_repo_dir))
            n_feats = len(skill_results.additional_features)
            n_sigs = len(skill_results.additional_signals)
            log_stage("4.7", "SkillPackExecutor",
                      f"SUCCESS ({n_feats} features, {n_sigs} signals)")

            # ── DEBUG: Save skill pack results ─────────────────────────
            _skill_debug = debug_path / "skill_results.json"
            with open(_skill_debug, "w", encoding="utf-8") as _f:
                json.dump(skill_results.model_dump(), _f, indent=2, default=str)
            print(f"[DEBUG] skill_results saved → {_skill_debug}")
        else:
            log_stage("4.5", "SkillPackMatcher", "SUCCESS (No packs matched — using standard pipeline)")
    except Exception as e:
        print(f"[SKILL PACKS] Stage 4.5/4.7 failed (non-blocking): {e}")
        log_stage("4.5", "SkillPackMatcher", f"SKIPPED ({e})")

    # ─── PHASE 2: ANALYSIS & FEATURE EXTRACTION ─────────────────────────
    log_stage("5", "FeatureExtractionAgent")
    chunks_list = chunks_data.get("chunks", [])
    # Pass repo_context as primary LLM input (README, structure, snippets)
    # Pass skill_results as supplementary context from activated skill packs
    feat_ext_result = extract_features(
        norm_modules, chunks_list,
        repo_context=repo_context,
        skill_results=skill_results,
    )
    raw_feats = feat_ext_result.model_dump()
    log_stage("5", "FeatureExtractionAgent", f"SUCCESS ({len(raw_feats['features'])} raw features)")

    log_stage("6", "FeatureValidator")
    feat_val_result = validate_features(raw_feats["features"])
    val_feats = feat_val_result.model_dump()
    val_feats_list = val_feats["validated_features"]
    log_stage("6", "FeatureValidator", f"SUCCESS ({len(val_feats_list)} validated features)")

    # ─── PHASE 2.5: PRUNE HALLUCINATIONS ───────────────────────────────
    log_stage("6.5", "Semantic Feature Pruning (LLM)")
    import os
    if os.environ.get("OPENAI_API_KEY"):
        from app.utils.llm_enrichment import prune_hallucinated_features
        # Pass full repo_context so pruning uses README as primary signal
        pruned_feats = prune_hallucinated_features(val_feats_list, repo_context)
        val_feats["validated_features"] = pruned_feats
        log_stage("6.5", "Semantic Feature Pruning (LLM)", f"SUCCESS ({len(pruned_feats)} features remain)")
    else:
        log_stage("6.5", "Semantic Feature Pruning (LLM)", "SKIPPED (No API Key)")

    val_feats_list = val_feats["validated_features"]

    log_stage("7", "ProductUnderstandingAgent")
    # Pass repo_context AND evidence so archetype detection has both README and structured facts
    prod_result = understand_product(val_feats_list, repo_context=repo_context, evidence=evidence)
    prod_dict = prod_result.model_dump()
    log_stage("7", "ProductUnderstandingAgent", f"SUCCESS (Archetype: {prod_dict['product']['name']})")

    # ─── PHASE 3: REQUIREMENT GENERATION ─────────────────────────────────
    log_stage("8", "FunctionalRequirementGenerator")
    fr_result = generate_requirements(val_feats_list)
    fr_dict = fr_result.model_dump()
    log_stage("8", "FunctionalRequirementGenerator", f"SUCCESS ({len(fr_dict['functional_requirements'])} FRs)")

    log_stage("9", "NonFunctionalRequirementGenerator")
    system_type = prod_dict['product']['name']
    # Build a flat list of tech label strings from dep_data + evidence.
    # This is project-type agnostic: it reads what the extractors actually found
    # (language, build_tool, platform, deps) — never invents or defaults to a generic stack.
    tech_stack_nfr = _build_tech_labels(dep_data, evidence)
    nfr_result = generate_nfrs(system_type=system_type, tech_stack=tech_stack_nfr)
    nfr_dict = nfr_result.model_dump()
    log_stage("9", "NonFunctionalRequirementGenerator", f"SUCCESS ({len(nfr_dict['non_functional_requirements'])} NFRs)")

    # ─── PHASE 3.5: LLM ENRICHMENT ───────────────────────────────────
    enriched_feat_list, prod_dict, artifacts = _try_enrich(
        val_feats_list, prod_dict, tech_stack_nfr, evidence
    )
    val_feats["validated_features"] = enriched_feat_list

    # ─── PHASE 3.6: BUSINESS UNDERSTANDING ─────────────────────────────
    # FIX (Bug 1.3): Call BusinessUnderstandingAgent explicitly so
    # compose_brd() receives product_type, primary_users, core_value.
    biz_result = understand_business(
        enriched_feat_list,
        system_type=prod_dict['product']['name']
    )
    biz_ctx = biz_result.model_dump()["business_context"]
    # Merge product summary into business context for Executive Summary richness
    biz_ctx["product_summary"] = prod_dict["product"].get("summary", "")
    biz_ctx["core_capabilities"] = prod_dict["product"].get("core_capabilities", [])
    biz_ctx["repo_name"] = scan_data.get("repo_name", "Unknown Repository")
    biz_ctx["tech_stack"] = tech_stack_nfr   # flat List[str] — consumed by all section composers
    biz_ctx["enterprise_artifacts"] = artifacts

    # ─── PHASE 3.7: BRD DEEP ENRICHMENT ─────────────────────────────────
    # Injects detailed, grounded LLM content into biz_ctx for every BRD section.
    # Dual-layer writing: plain English for business + technical note for engineers.
    # Falls back gracefully if OPENAI_API_KEY is not set or any call fails.
    try:
        from app.analysis.brd_enrichment_agent import enrich_brd_context
        biz_ctx = enrich_brd_context(
            biz_ctx=biz_ctx,
            features=enriched_feat_list,
            fr_dict=fr_dict,
            nfr_dict=nfr_dict,
            repo_context=repo_context,
        )
    except Exception as e:
        print(f"[BRD ENRICHMENT] Phase 3.7 failed, continuing without enrichment. Error: {e}")
    log_stage("10", "BRDComposer & FixLoop")
    # FIX (Bug 1.1): Pass correct keyword argument names matching compose_brd() signature.
    initial_markdown = compose_brd(
        business_context=biz_ctx,
        features=enriched_feat_list,
        functional_requirements=fr_dict["functional_requirements"],
        non_functional_requirements=nfr_dict["non_functional_requirements"],
        evidence=evidence,
    )
    
    loop_result = run_fix_loop(
        initial_markdown,
        max_iterations=2,
        features=enriched_feat_list,
        functional_requirements=fr_dict["functional_requirements"],
        evidence=evidence,
    )
    final_markdown = loop_result["final_markdown"]
    final_val = loop_result["final_validation"]
    
    score = final_val["score"]
    status = "PASSED" if score >= 0.85 else "FAILED"
    log_stage("10", "BRDComposer & FixLoop", f"SUCCESS ({status} with score {score:.2f})")

    if final_val["issues"]:
        print("⚠️ Remaining Issues:")
        for issue in final_val["issues"]:
            print(f"   - {issue}")

    # Build standard Phase 1 canonical final payload for complete compatibility
    validation_data = validate_context(normalized_data)
    final_payload = build_final_output(
        scan_data,
        classified_data,
        chunks_data,
        normalized_data,
        validation_data
    )

    # ── DEBUG: Save final payload and validation data to JSON ─────────────
    _final_payload_debug = {
        "business_context": biz_ctx,
        "features": enriched_feat_list,
        "functional_requirements": fr_dict["functional_requirements"],
        "non_functional_requirements": nfr_dict["non_functional_requirements"],
    }
    for _fname, _data in [
        ("final_payload.json",    _final_payload_debug),
        ("validation_data.json",  final_val),
    ]:
        _fpath = debug_path / _fname
        with open(_fpath, "w", encoding="utf-8") as _f:
            json.dump(_data, _f, indent=2, default=str)
        print(f"[DEBUG] Saved → {_fpath}")

    return {
        "final_payload": final_payload,
        "final_markdown": final_markdown,
        "final_validation": final_val,
        "biz_ctx": biz_ctx,
        "features": enriched_feat_list,
        "functional_requirements": fr_dict["functional_requirements"],
        "non_functional_requirements": nfr_dict["non_functional_requirements"],
        "repo_name": repo_name,
        "brd_path": str(brd_path),
    }


def run_end_to_end(repo_url: str, output_dir: str):
    try:
        res = run_full_pipeline_service(repo_url, output_dir)
        final_markdown = res["final_markdown"]
        repo_name = res["repo_name"]

        # Save final BRD into the per-repo brd/ folder
        brd_out_path = Path(res["brd_path"]) / f"BRD_{repo_name}.md"
        with open(brd_out_path, "w", encoding="utf-8") as f:
            f.write(final_markdown)

        print("\n==================================================")
        print("✅ BRD PIPELINE COMPLETED SUCCESSFULLY")
        print(f"📄 BRD saved to : {brd_out_path}")
        print(f"🗂  Debug JSONs  : {res['brd_path'].replace('/brd', '/debug')}")
        print("==================================================\n")

    except Exception as e:
        import traceback
        print("\n==================================================")
        print("❌ PIPELINE FAILED")
        traceback.print_exc()
        print("==================================================\n")
        sys.exit(1)


def run_pipeline(repo_url: str, output_path: str = None) -> dict:
    """
    Phase 1 pipeline: clone → scan → classify → chunk → aggregate → normalize → validate.
    Returns the canonical final payload dict consumed by analyze-and-convert.
    All imports are already at module level; no redundant local imports needed.
    """
    from app.context.validator import validate_context
    from app.output.final_output_builder import build_final_output

    out_dir = output_path if output_path else "runtime/pipeline_out"
    out_path_obj = Path(out_dir)
    out_path_obj.mkdir(parents=True, exist_ok=True)

    # Derive a unique, repo-specific clone directory so runs never cross-contaminate
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")

    # Per-repo layout: debug/ for JSONs, repo/src/ for cloned code
    repo_out   = out_path_obj / repo_name
    debug_path = repo_out / "debug"
    dest_repo_dir = repo_out / "repo" / "src"
    for _d in (debug_path, dest_repo_dir):
        _d.mkdir(parents=True, exist_ok=True)

    # Always clone fresh — never reuse a stale directory from a previous run
    scan_data = scan_repository(repo_url, str(dest_repo_dir), skip_clone=False)
    if "error" in scan_data:
        raise RuntimeError(f"RepoScanner failed: {scan_data['error']}")

    # ── DEBUG: Save scan_data (Stage 1 output) to JSON ────────────────────
    with open(debug_path / "scan_data.json", "w", encoding="utf-8") as _f:
        json.dump(scan_data, _f, indent=2, default=str)
    print(f"[DEBUG] scan_data saved → {debug_path / 'scan_data.json'}")

    classified_data = run_classifier(scan_data)

    # ── DEBUG: Save classified_data (Stage 2 output) to JSON ───────────────
    with open(debug_path / "classified_data.json", "w", encoding="utf-8") as _f:
        json.dump(classified_data, _f, indent=2, default=str)
    print(f"[DEBUG] classified_data saved → {debug_path / 'classified_data.json'}")

    # Pass the actual cloned repo dir so content_processor reads the right files
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

    # ── DEBUG: Dump intermediate pipeline data to JSON files ──────────────
    _debug_files = {
        "aggregated_data.json": aggregated_data,
        "normalized_data.json": normalized_data,
        "validation_data.json": validation_data,
        "final_payload.json":   final_payload,
        "ChunkData.json":       chunks_data,
    }
    for _fname, _data in _debug_files.items():
        _fpath = debug_path / _fname
        with open(_fpath, "w", encoding="utf-8") as _f:
            json.dump(_data, _f, indent=2, default=str)
        print(f"[DEBUG] Saved → {_fpath}")

    return final_payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the full Analyst-Agent pipeline to generate a BRD.")
    parser.add_argument("repo_url", help="URL of the target GitHub repository")
    parser.add_argument("--outdir", default="runtime/pipeline_out", help="Directory to store outputs")
    args = parser.parse_args()

    run_end_to_end(args.repo_url, args.outdir)

