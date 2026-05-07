"""
runner.py — Master Pipeline Orchestrator
-----------------------------------------
Executes the full 5-phase BRD generation pipeline:

  Phase 1 — Context Extraction
    RepoScanner → FileClassifier → ContentProcessor → ContextAggregator → Normalizer

  Phase 2 — Feature Analysis
    FeatureExtractionAgent → FeatureValidator → ProductUnderstandingAgent → BusinessUnderstandingAgent

  Phase 3 — Requirement Generation
    FunctionalRequirementGenerator → NonFunctionalRequirementGenerator

  Phase 4 — Technical Signal Extraction (new extractors)
    DependencyExtractor → EntityExtractor → ApiExtractor → DefectExtractor → EvidenceBundle

  Phase 5 — LLM BRD Composition & Validation
    LLMBRDComposer (16 grounded LLM calls) → LLMBRDValidator → Final BRD

Design decisions:
  - Each phase logs start/complete with duration via StageTimer.
  - Phase 4 extractors are optional: failure is logged but never crashes the pipeline.
  - Phase 5 LLM composer falls back to deterministic mode if OPENAI_API_KEY is missing.
  - All print() replaced with structured logger calls.
  - run_pipeline() (called by the API) and run_end_to_end() (CLI) share the same core logic.
"""
from __future__ import annotations

import sys
import json
import argparse
import os
from pathlib import Path
from typing import Any, Dict, List

# ── Logging (must come first) ──────────────────────────────────────────────
from app.utils.logger import get_logger, StageTimer, log

logger = get_logger(__name__)

# ── Phase 1: Context Extraction ────────────────────────────────────────────
from app.eca.repo_scanner      import scan_repository
from app.eca.file_classifier   import run_classifier
from app.eca.content_processor import run_content_processor
from app.context.aggregator    import aggregate_context
from app.context.normalizer    import normalize_context

# ── Phase 2: Feature Analysis ──────────────────────────────────────────────
from app.analysis.feature_extraction_agent      import extract_features
from app.analysis.feature_validator             import validate_features
from app.analysis.product_understanding_agent   import understand_product
from app.analysis.business_understanding_agent  import understand_business

# ── Phase 3: Requirement Generation ───────────────────────────────────────
from app.analysis.functional_requirement_generator     import generate_requirements
from app.analysis.non_functional_requirement_generator import generate_nfrs

# ── Phase 4: Technical Signal Extraction ──────────────────────────────────
from app.eca.dependency_extractor import extract_dependencies
from app.eca.entity_extractor     import extract_entities
from app.eca.api_extractor        import extract_api_endpoints
from app.eca.defect_extractor     import extract_defects
from app.analysis.evidence_bundle import build_evidence_bundle

# ── Phase 5: LLM BRD Composition & Validation ─────────────────────────────
from app.analysis.llm_brd_composer  import compose_brd_llm
from app.analysis.llm_brd_validator import validate_brd_llm


# ---------------------------------------------------------------------------
# LLM Enrichment Helper (optional pre-step)
# ---------------------------------------------------------------------------

def _try_enrich(
    val_feats_list: List[Dict],
    prod_dict: Dict,
) -> tuple[List[Dict], Dict]:
    """
    Attempt LLM enrichment of feature descriptions.
    Silently skips if OPENAI_API_KEY is not configured or any error occurs.
    Returns (enriched_features, updated_prod_dict).
    """
    if not os.environ.get("OPENAI_API_KEY"):
        log(logger.info, "llm_enrichment.skipped", reason="OPENAI_API_KEY not set")
        return val_feats_list, prod_dict

    try:
        from app.utils.llm_enrichment import enrich_features, enrich_core_value
        enriched   = enrich_features(val_feats_list)
        core_value = enrich_core_value(enriched)
        updated    = dict(prod_dict)
        updated["core_value"] = core_value
        log(logger.info, "llm_enrichment.complete", features=len(enriched))
        return enriched, updated
    except Exception as exc:
        log(logger.warning, "llm_enrichment.failed", error=str(exc), action="using_original")
        return val_feats_list, prod_dict


# ---------------------------------------------------------------------------
# Phase 4: Technical Signal Extraction (safe wrappers)
# ---------------------------------------------------------------------------

def _run_technical_extractors(dest_repo_dir: Path) -> Dict[str, Any]:
    """
    Run all four technical signal extractors.
    Each extractor is wrapped defensively — failure returns an empty result,
    never propagating to crash the pipeline.

    Returns a dict with keys: dependencies, entities, api_endpoints, defects.
    """
    results: Dict[str, Any] = {
        "dependencies": {"dependencies": [], "build_tool": "unknown", "language": "unknown", "uses_jcenter": False},
        "entities":     {"entities": []},
        "api_endpoints": {"endpoints": [], "grpc_rpcs": []},
        "defects":      {"defects": []},
    }

    extractors = [
        ("dependencies",  extract_dependencies,  "DependencyExtractor"),
        ("entities",      extract_entities,      "EntityExtractor"),
        ("api_endpoints", extract_api_endpoints, "ApiExtractor"),
        ("defects",       extract_defects,       "DefectExtractor"),
    ]

    for key, fn, name in extractors:
        with StageTimer(logger, f"extractor.{name.lower()}"):
            try:
                results[key] = fn(dest_repo_dir)
                log(logger.info, f"extractor.{key}.ok",
                    count=len(results[key].get(list(results[key].keys())[0], [])))
            except Exception as exc:
                log(logger.error, f"extractor.{key}.failed", error=str(exc), action="using_empty")

    return results


# ---------------------------------------------------------------------------
# Core Pipeline Logic (shared by API and CLI)
# ---------------------------------------------------------------------------

def run_pipeline(repo_url: str, output_path: str | None = None) -> Dict[str, Any]:
    """
    Execute Phase 1 context extraction only and return the raw payload.
    Called by the /analyze endpoint and as the first step of run_end_to_end.
    """
    from app.context.validator         import validate_context
    from app.output.final_output_builder import build_final_output

    out_dir  = output_path or "runtime/pipeline_out"
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    dest_repo_dir = out_path / "runner_repo"

    with StageTimer(logger, "phase1.scan"):
        scan_data = scan_repository(repo_url, str(dest_repo_dir), skip_clone=False)
        if "error" in scan_data:
            raise RuntimeError(f"RepoScanner failed: {scan_data['error']}")

    with StageTimer(logger, "phase1.classify"):
        classified_data = run_classifier(scan_data)

    with StageTimer(logger, "phase1.content"):
        chunks_data = run_content_processor(classified_data, dest_repo_dir)

    with StageTimer(logger, "phase1.aggregate"):
        aggregated_data = aggregate_context(chunks_data)
        normalized_data = normalize_context(aggregated_data)

    validation_data = validate_context(normalized_data)

    final_payload = build_final_output(
        scan_data, classified_data, chunks_data, normalized_data, validation_data,
    )

    # Attach raw scan_data for downstream use (extractors need repo path)
    final_payload["_scan_data"]     = scan_data
    final_payload["_dest_repo_dir"] = str(dest_repo_dir)
    final_payload["_chunks"]        = chunks_data.get("chunks", [])

    return final_payload


def run_full_brd_pipeline(
    repo_url:    str,
    output_path: str | None = None,
) -> Dict[str, Any]:
    """
    Execute the full 5-phase BRD pipeline.
    Returns a dict containing: markdown, validation, evidence_bundle, final_payload.

    This is the main entry point for the /analyze-and-convert API endpoint.
    """
    out_dir  = output_path or "runtime/pipeline_out"
    out_path = Path(out_dir)

    log(logger.info, "pipeline.start", repo=repo_url)

    # ── Phase 1: Context Extraction ────────────────────────────────────────
    logger.info("phase1.start")
    final_payload  = run_pipeline(repo_url, out_dir)
    scan_data      = final_payload.pop("_scan_data", {})
    dest_repo_dir  = Path(final_payload.pop("_dest_repo_dir", out_dir))
    chunks_list    = final_payload.pop("_chunks", [])

    # FIX (Bug 1.2): key is "modules", not "normalized_modules"
    norm_modules = final_payload.get("modules", final_payload.get("normalized_modules", []))
    log(logger.info, "phase1.complete", modules=len(norm_modules), chunks=len(chunks_list))

    # ── Phase 2: Feature Analysis ─────────────────────────────────────────
    logger.info("phase2.start")
    with StageTimer(logger, "phase2.feature_extraction"):
        feat_ext    = extract_features(norm_modules, chunks_list)
        raw_feats   = feat_ext.model_dump()["features"]

    with StageTimer(logger, "phase2.feature_validation"):
        val_result  = validate_features(raw_feats)
        val_feats   = val_result.model_dump()["validated_features"]

    with StageTimer(logger, "phase2.product_understanding"):
        prod_result = understand_product(val_feats)
        prod_dict   = prod_result.model_dump()

    with StageTimer(logger, "phase2.llm_enrichment"):
        val_feats, prod_dict = _try_enrich(val_feats, prod_dict)

    with StageTimer(logger, "phase2.business_understanding"):
        biz_result = understand_business(val_feats, system_type=prod_dict["product"]["name"])
        biz_ctx    = biz_result.model_dump()["business_context"]
        biz_ctx["product_summary"]   = prod_dict["product"].get("summary", "")
        biz_ctx["core_capabilities"] = prod_dict["product"].get("core_capabilities", [])
        biz_ctx["repo_name"]         = scan_data.get("repo_name", repo_url.rstrip("/").rsplit("/", 1)[-1])

    log(logger.info, "phase2.complete", features=len(val_feats))

    # ── Phase 3: Requirement Generation ───────────────────────────────────
    logger.info("phase3.start")
    with StageTimer(logger, "phase3.fr_generation"):
        fr_result = generate_requirements(val_feats)
        frs       = fr_result.model_dump()["functional_requirements"]

    with StageTimer(logger, "phase3.nfr_generation"):
        nfr_result = generate_nfrs(system_type=prod_dict["product"]["name"], tech_stack=[])
        nfrs       = nfr_result.model_dump()["non_functional_requirements"]

    log(logger.info, "phase3.complete", frs=len(frs), nfrs=len(nfrs))

    # ── Phase 4: Technical Signal Extraction ──────────────────────────────
    logger.info("phase4.start")
    tech_signals = _run_technical_extractors(dest_repo_dir)

    with StageTimer(logger, "phase4.evidence_bundle"):
        bundle = build_evidence_bundle(
            scan_data        = scan_data,
            validated_feats  = val_feats,
            frs              = frs,
            nfrs             = nfrs,
            biz_ctx          = biz_ctx,
            chunks           = chunks_list,
            dependencies     = tech_signals["dependencies"],
            entities         = tech_signals["entities"],
            api_endpoints    = tech_signals["api_endpoints"],
            defects          = tech_signals["defects"],
        )

    log(logger.info, "phase4.complete",
        deps=len(bundle.get("dependencies", [])),
        entities=len(bundle.get("entities", [])),
        endpoints=len(bundle.get("endpoints", [])),
        defects=len(bundle.get("defects", [])))

    # ── Phase 5: LLM BRD Composition & Validation ─────────────────────────
    logger.info("phase5.start")
    with StageTimer(logger, "phase5.llm_composition"):
        final_markdown = compose_brd_llm(bundle)

    with StageTimer(logger, "phase5.validation"):
        validation = validate_brd_llm(final_markdown, bundle)

    log(logger.info, "phase5.complete",
        score=validation["score"],
        verdict=validation["verdict"],
        issues=len(validation["issues"]))

    # ── Save outputs ────────────────────────────────────────────────────────
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "Target_BRD.md").write_text(final_markdown, encoding="utf-8")
    (out_path / "evidence_bundle.json").write_text(
        json.dumps(bundle, indent=2, default=str), encoding="utf-8"
    )

    log(logger.info, "pipeline.complete",
        repo=bundle.get("repo_name"), brd=str(out_path / "Target_BRD.md"))

    return {
        "markdown":        final_markdown,
        "validation":      validation,
        "evidence_bundle": bundle,
        "final_payload":   final_payload,
    }


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def run_end_to_end(repo_url: str, output_dir: str) -> None:
    """CLI wrapper around run_full_brd_pipeline with human-readable output."""
    log(logger.info, "cli.start", repo=repo_url, outdir=output_dir)
    try:
        result = run_full_brd_pipeline(repo_url, output_dir)
        val    = result["validation"]
        log(logger.info, "cli.done",
            score=val["score"], verdict=val["verdict"],
            brd=str(Path(output_dir) / "Target_BRD.md"))
        if val["issues"]:
            for iss in val["issues"][:5]:
                log(logger.warning, "validation.issue", detail=iss)
    except Exception:
        logger.error("cli.pipeline_failed")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyst Agent — Full BRD Pipeline")
    parser.add_argument("repo_url", help="GitHub repository URL")
    parser.add_argument("--outdir", default="runtime/pipeline_out", help="Output directory")
    args = parser.parse_args()
    run_end_to_end(args.repo_url, args.outdir)
