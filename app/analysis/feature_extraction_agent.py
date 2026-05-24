"""
feature_extraction_agent.py — Layer 3 Tool
-------------------------------------------
FeatureExtractionAgent

Inputs:
  - normalized_modules : List of normalized module dicts
      { "id": str, "name": str, "files": [str], "confidence": float }
  - chunks             : List of chunk dicts (content used as summarized context)
      { "chunk_id": str, "file_path": str, "category": str, "content": str }

Output (strict JSON):
  {
    "features": [
      {
        "id": str,
        "name": str,
        "description": str,
        "source_modules": [str],
        "confidence": float
      }
    ]
  }

Extraction logic:
  Uses an LLM to dynamically interpret the repository structure and content,
  identifying genuine functional and technical capabilities without relying
  on hardcoded generic keyword dictionaries.
"""

from __future__ import annotations

import json
import argparse
import sys
import os
import re
from pathlib import Path
from typing import Dict, Any, List

from app.schemas.models import ExtractedFeature, FeatureExtractionResult

# Attempt to load environment variables and the LLM client
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(dotenv_path=_env_path, override=False)
except ImportError:
    pass

try:
    from app.utils.llm_client import llm_json_call
except ImportError:
    llm_json_call = None


# ---------------------------------------------------------------------------
# Confidence Calibration — Cross-File Boosting & Negative Signals
# ---------------------------------------------------------------------------

# File-path patterns that are test / mock / fixture / example artefacts.
# Features evidenced ONLY by these files have inflated confidence.
_NEGATIVE_SIGNAL_RE = re.compile(
    r"(^|/)("
    r"test[s_]?|spec[s_]?|mock[s_]?|fixture[s_]?|stub[s_]?|"
    r"fake[s_]?|__test__|__spec__|__mock__|"
    r"example[s_]?|sample[s_]?|demo[s_]?"
    r")",
    re.IGNORECASE,
)


def _is_negative_signal(filepath: str) -> bool:
    """Return True if a file path looks like a test / mock / fixture."""
    return bool(_NEGATIVE_SIGNAL_RE.search(filepath))


def _calibrate_confidence(features: List[ExtractedFeature], chunks: List[Dict]) -> List[ExtractedFeature]:
    """
    Post-process extracted features to calibrate confidence using two signals:

    1. **Cross-file boosting** — A feature mentioned in many distinct source files
       is more likely to be real. We count how many *unique* chunk file-paths
       reference keywords from the feature name and boost accordingly.

    2. **Negative-signal penalty** — If ALL evidence files for a feature are
       tests/mocks/fixtures, confidence is reduced by 0.20. If SOME are tests,
       reduced by 0.10.

    The result is clamped to [0.1, 1.0].
    """
    if not chunks:
        return features

    # Pre-index: lowercase file paths from chunks for keyword search
    chunk_paths = [c.get("file_path", "").lower() for c in chunks]
    chunk_contents = [c.get("content", "").lower()[:500] for c in chunks]

    calibrated = []
    for feat in features:
        conf = feat.confidence
        name_lower = feat.name.lower().replace(" ", "_")
        # Extract meaningful keywords (skip very short tokens)
        keywords = [kw for kw in name_lower.split("_") if len(kw) >= 3]

        if not keywords:
            calibrated.append(feat)
            continue

        # --- Signal 1: Cross-file boosting ---
        # Count distinct files whose path OR content snippet mentions ≥1 keyword
        matching_files: set[str] = set()
        for i, (fp, content) in enumerate(zip(chunk_paths, chunk_contents)):
            for kw in keywords:
                if kw in fp or kw in content:
                    matching_files.add(fp)
                    break

        file_count = len(matching_files)
        if file_count >= 6:
            conf += 0.10      # Strong cross-file presence
        elif file_count >= 3:
            conf += 0.05      # Moderate presence
        elif file_count == 0:
            conf -= 0.10      # No file evidence at all

        # --- Signal 2: Negative-signal penalty ---
        source_mods = feat.source_modules or []
        if source_mods:
            negative_count = sum(1 for m in source_mods if _is_negative_signal(m))
            if negative_count == len(source_mods):
                # ALL evidence is tests/mocks → heavy penalty
                conf -= 0.20
            elif negative_count > 0:
                # SOME evidence is tests → mild penalty
                conf -= 0.10

        # Also check matching_files for negative signals
        if matching_files:
            neg_file_count = sum(1 for fp in matching_files if _is_negative_signal(fp))
            neg_ratio = neg_file_count / len(matching_files)
            if neg_ratio >= 0.8:
                conf -= 0.10  # Predominantly test files

        # Clamp
        conf = round(max(0.1, min(1.0, conf)), 2)

        calibrated.append(ExtractedFeature(
            id=feat.id,
            name=feat.name,
            description=feat.description,
            source_modules=feat.source_modules,
            confidence=conf,
        ))

    return calibrated


# ---------------------------------------------------------------------------
# LLM Extraction Prompt
# ---------------------------------------------------------------------------

DYNAMIC_EXTRACTION_PROMPT = """\
You are an expert product analyst and software architect performing feature extraction for a Business Requirements Document.

I am providing you with a STRUCTURED CONTEXT about a software repository. Use the sources below in PRIORITY ORDER:

  PRIORITY 1 — README / Package Description: This is the ground truth for what the product DOES.
  PRIORITY 2 — Application Structure (routes, components, types): These reveal what screens/workflows exist.
  PRIORITY 3 — Business Logic Snippets: These reveal the data model and rules.
  PRIORITY 4 — Tech Stack: Informs NFRs only, NOT features.

YOUR TASK:
  Extract the REAL PRODUCT FEATURES of this application — what it does for its users, not how it is built.
  Features should be USER-FACING or BUSINESS-LOGIC capabilities, not build tools or framework boilerplate.

NEGATIVE EXAMPLES (do NOT extract these as features):
  BAD: "TypeScript Compilation", "TailwindCSS Styling", "Vite Build Toolchain", "SSR Configuration"
  GOOD: "ATS Resume Scoring", "Job-Specific Analysis", "PDF Upload and Parsing", "Multi-Dimensional Feedback"

For confidence scoring:
  0.9-1.0 : Feature explicitly described in README with code evidence
  0.75-0.89: Feature evident from route/component names without explicit README mention
  0.5-0.74 : Feature inferred from code snippets or type definitions
  < 0.5   : Do not include — insufficient evidence

Return ONLY a valid JSON object matching this schema:
{
  "features": [
    {
      "name": "Feature Name (Title Case, product-facing)",
      "description": "1-2 sentences: what it does for users and how (grounded in evidence).",
      "source_modules": ["route/component/file names that prove this feature exists"],
      "confidence": 0.95
    }
  ]
}
"""


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def extract_features(
    normalized_modules: List[Dict],
    chunks: List[Dict],
    repo_context: Dict = None,
    skill_results = None,
) -> FeatureExtractionResult:
    """
    Dynamically extract features using an LLM based on repository contents.

    If repo_context is provided (from RepoContextBuilder), it is used as the
    primary LLM input — README, structure, tech stack, and key snippets.
    Falls back to normalized_modules + chunk snippets if repo_context is absent.

    If skill_results is provided (SkillExecutionResult from activated skill packs),
    skill-extracted features are merged into the final result and skill signals
    are injected into the LLM context for richer extraction.

    Post-processes with confidence calibration (cross-file boost + negative signals).
    """
    if llm_json_call is None or not os.environ.get("OPENAI_API_KEY"):
        print("[LLM] Feature extraction falling back to generic baseline (No API Key).", file=sys.stderr)
        result = _fallback_extraction(normalized_modules)
        result = FeatureExtractionResult(features=_calibrate_confidence(result.features, chunks))
        # Merge skill-extracted features even in fallback mode
        if skill_results:
            result = _merge_skill_features(result, skill_results)
        return result

    # ── Build LLM context string ─────────────────────────────────────────
    if repo_context:
        context_str = _build_rich_context_str(repo_context)
    else:
        # Legacy fallback: module names + chunk snippets (old behaviour)
        module_names = [m.get("name", "unknown") for m in normalized_modules]
        chunk_summaries = []
        for c in chunks[:50]:
            fp = c.get("file_path", "")
            content = c.get("content", "")[:300].replace("\n", " ")
            chunk_summaries.append(f"File: {fp} | Content snippet: {content}")
        context_str = (
            f"DETECTED MODULES: {', '.join(module_names)}\n\n"
            f"FILE SNIPPETS:\n" + "\n".join(chunk_summaries)
        )

    # ── Inject skill pack signals into LLM context ─────────────────────
    if skill_results and hasattr(skill_results, 'additional_signals'):
        skill_signals = skill_results.additional_signals
        if skill_signals:
            signals_text = "\n".join(f"  - {k}: {v}" for k, v in skill_signals.items()
                                     if not isinstance(v, (dict, list)) or len(str(v)) < 200)
            context_str += (
                f"\n\nSKILL PACK ANALYSIS SIGNALS (pre-extracted by domain-specific analysers):\n"
                f"{signals_text}"
            )
        # Also inject BRD section hints as extraction guidance
        if hasattr(skill_results, 'brd_section_hints') and skill_results.brd_section_hints:
            hints_text = "\n".join(f"  - {k}: {v}" for k, v in skill_results.brd_section_hints.items())
            context_str += f"\n\nDOMAIN-SPECIFIC EXTRACTION GUIDANCE:\n{hints_text}"

    try:
        result = llm_json_call(DYNAMIC_EXTRACTION_PROMPT, context_str, max_tokens=2000)

        extracted = []
        raw_feats = result.get("features", [])
        for idx, rf in enumerate(raw_feats, start=1):
            extracted.append(ExtractedFeature(
                id=f"feat-{idx:03d}",
                name=rf.get("name", "Unknown Feature"),
                description=rf.get("description", "No description provided."),
                source_modules=rf.get("source_modules", []),
                confidence=float(rf.get("confidence", 0.8))
            ))

        if not extracted:
            print("[LLM] Dynamic feature extraction returned empty list. Using fallback.", file=sys.stderr)
            fallback = _fallback_extraction(normalized_modules)
            result_obj = FeatureExtractionResult(features=_calibrate_confidence(fallback.features, chunks))
            if skill_results:
                result_obj = _merge_skill_features(result_obj, skill_results)
            return result_obj

        # Apply confidence calibration post-processing
        calibrated = _calibrate_confidence(extracted, chunks)
        result_obj = FeatureExtractionResult(features=calibrated)

        # Merge skill-extracted features
        if skill_results:
            result_obj = _merge_skill_features(result_obj, skill_results)

        return result_obj

    except Exception as e:
        print(f"[LLM] Dynamic feature extraction failed: {e}. Using fallback.", file=sys.stderr)
        fallback = _fallback_extraction(normalized_modules)
        result_obj = FeatureExtractionResult(features=_calibrate_confidence(fallback.features, chunks))
        if skill_results:
            result_obj = _merge_skill_features(result_obj, skill_results)
        return result_obj


def _merge_skill_features(
    result: FeatureExtractionResult,
    skill_results,
) -> FeatureExtractionResult:
    """
    Merge skill-pack-extracted features into the main feature list.
    De-duplicates by normalised feature name (lowercase, underscored).
    Skill features start with the next available feat-NNN id.
    """
    if not skill_results or not hasattr(skill_results, 'additional_features'):
        return result

    skill_feats = skill_results.additional_features
    if not skill_feats:
        return result

    # Build set of existing normalised names for dedup
    existing_names = set()
    for f in result.features:
        existing_names.add(f.name.lower().replace(" ", "_"))

    next_id = len(result.features) + 1
    merged = list(result.features)

    for sf in skill_feats:
        name = sf.get("name", "")
        normalised = name.lower().replace(" ", "_")
        if normalised in existing_names or not name:
            continue  # skip duplicates

        existing_names.add(normalised)
        merged.append(ExtractedFeature(
            id=f"feat-{next_id:03d}",
            name=name,
            description=sf.get("description", f"Feature extracted by skill pack: {name}"),
            source_modules=sf.get("source_modules", []),
            confidence=float(sf.get("confidence", 0.75)),
        ))
        next_id += 1

    if len(merged) > len(result.features):
        added = len(merged) - len(result.features)
        print(f"[SKILL MERGE] Added {added} skill-extracted features (total: {len(merged)}).", file=sys.stderr)

    return FeatureExtractionResult(features=merged)


def _build_rich_context_str(repo_context: Dict) -> str:
    """
    Convert RepoContext dict into a structured string for the LLM prompt.
    Sections are clearly labelled and ordered by priority.
    """
    signals   = repo_context.get("intent_signals", {})
    tech      = repo_context.get("tech_stack", {})
    structure = repo_context.get("structure", {})
    snippets  = repo_context.get("key_file_snippets", [])
    note      = repo_context.get("confidence_note", "")

    parts: List[str] = []

    # PRIORITY 1: README / package description
    readme = signals.get("readme", "").strip()
    if readme:
        src = signals.get("source", "README")
        parts.append(f"=== PRIORITY 1: PRODUCT DOCUMENTATION (Source: {src}) ===\n{readme}")
    else:
        pkg_name = signals.get("package_name", "")
        pkg_desc = signals.get("package_description", "")
        pkg_kw   = ", ".join(signals.get("package_keywords", []))
        if pkg_desc:
            parts.append(
                f"=== PRIORITY 1: PACKAGE MANIFEST (no README found) ===\n"
                f"Name: {pkg_name}\nDescription: {pkg_desc}\nKeywords: {pkg_kw}"
            )
        else:
            parts.append(f"=== PRIORITY 1: [NO DOCUMENTATION] {note} ===")

    # PRIORITY 2: Application structure
    if any(structure.values()):
        lines = ["=== PRIORITY 2: APPLICATION STRUCTURE ==="]
        for role, files in structure.items():
            if files:
                lines.append(f"  {role.capitalize()}: {', '.join(files[:20])}")
        parts.append("\n".join(lines))

    # PRIORITY 3: Business logic snippets
    biz_snippets = [s for s in snippets if s.get("reason") == "business_logic"]
    if biz_snippets:
        lines = ["=== PRIORITY 3: BUSINESS LOGIC SNIPPETS ==="]
        for s in biz_snippets:
            lines.append(f"  [{s['file']}]: {s['content'][:300]}")
        parts.append("\n".join(lines))

    # Entry point snippets
    ep_snippets = [s for s in snippets if s.get("reason") == "entry_point"]
    if ep_snippets:
        lines = ["=== ENTRY POINT FILES ==="]
        for s in ep_snippets:
            lines.append(f"  [{s['file']}]: {s['content'][:300]}")
        parts.append("\n".join(lines))

    # PRIORITY 4: Tech stack
    if tech:
        tech_str = "\n".join(f"  {k}: {v}" for k, v in tech.items())
        parts.append(f"=== PRIORITY 4: TECH STACK ===\n{tech_str}")

    return "\n\n".join(parts)


def _fallback_extraction(normalized_modules: List[Dict]) -> FeatureExtractionResult:
    """Deterministic fallback if LLM is unavailable or fails."""
    candidates = []
    for idx, mod in enumerate(normalized_modules, start=1):
        name = mod.get("name", "Unknown Module")
        candidates.append(
            ExtractedFeature(
                id=f"feat-{idx:03d}",
                name=name.replace("_", " ").title() + " Component",
                description=f"Core architectural component encompassing {name}.",
                source_modules=[name],
                confidence=0.7
            )
        )
    return FeatureExtractionResult(features=candidates)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "FeatureExtractionAgent: Extract dynamic features "
            "from normalized_modules + chunks using an LLM. Returns JSON only."
        )
    )
    parser.add_argument(
        "--modules",
        default="runtime/outputs/normalized_context.json",
        help="Path to normalized_context.json",
    )
    parser.add_argument(
        "--chunks",
        default="runtime/outputs/chunks_output.json",
        help="Path to chunks_output.json",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional path to write output JSON",
    )
    args = parser.parse_args()

    modules_path = Path(args.modules)
    chunks_path = Path(args.chunks)

    for p in (modules_path, chunks_path):
        if not p.exists():
            print(f"[ERROR] File not found: {p}", file=sys.stderr)
            raise SystemExit(1)

    with open(modules_path, encoding="utf-8") as fh:
        modules_raw = json.load(fh)

    with open(chunks_path, encoding="utf-8") as fh:
        chunks_raw = json.load(fh)

    normalized_modules: List[Dict] = (
        modules_raw.get("normalized_modules", modules_raw)
        if isinstance(modules_raw, dict)
        else modules_raw
    )
    chunks: List[Dict] = (
        chunks_raw.get("chunks", chunks_raw)
        if isinstance(chunks_raw, dict)
        else chunks_raw
    )

    result = extract_features(normalized_modules, chunks)
    output_json = result.model_dump_json(indent=2)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(output_json)
        print(f"[OK] Features written to {out_path}", file=sys.stderr)
    else:
        print(output_json)

    print(f"\n[SUMMARY] features_extracted={len(result.features)}", file=sys.stderr)