"""
payload_converter.py — Layer 3 Tool
-------------------------------------
Converts the pipeline's final canonical payload into:
  1. List[AnalysisFeature]  — product-level features
  2. List[Requirement]      — SHALL-style functional requirements
  3. MinimalBRD             — structured, minimal BRD as JSON

CONTRACT:
  Input  : Final payload dict (schema: repo_name, files, modules, chunks, validation)
  Output : MinimalBRD  (defined in app/schemas/models.py)

Rules:
  - All derivations are deterministic and rule-based (no LLM calls)
  - Confidence is inherited directly from pipeline data; never inflated
  - If a field cannot be derived from input, it is omitted or set to lowest-confidence value
  - Output is minimal — only what is evidenced by input data

Usage (CLI):
  python -m app.analysis.payload_converter --payload runtime/outputs/final_payload.json
  python -m app.analysis.payload_converter --payload runtime/outputs/final_payload.json --out runtime/outputs/brd.json
"""

import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple

from app.schemas.models import AnalysisFeature, Requirement, MinimalBRD

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maps module/directory name fragments → feature category
CATEGORY_MAP: Dict[str, str] = {
    "api":        "api",
    "routes":     "api",
    "endpoints":  "api",
    "main":       "core_pipeline",
    "pipeline":   "core_pipeline",
    "runner":     "core_pipeline",
    "eca":        "core_pipeline",
    "scanner":    "core_pipeline",
    "classifier": "core_pipeline",
    "processor":  "core_pipeline",
    "aggregator": "core_pipeline",
    "normalizer": "core_pipeline",
    "validator":  "core_pipeline",
    "builder":    "feature_detection",
    "context":    "feature_detection",
    "output":     "core_pipeline",
    "schema":     "core_pipeline",
}

# Priority mapping: category → Requirement priority
PRIORITY_MAP: Dict[str, str] = {
    "core_pipeline":    "High",
    "api":              "High",
    "feature_detection": "Medium",
    "unknown":          "Low",
}

# ---------------------------------------------------------------------------
# Stage 1: Feature extraction
# ---------------------------------------------------------------------------

def _infer_category(sources: List[str]) -> str:
    """Infer a feature category from its source file paths deterministically."""
    for src in sources:
        lower = src.lower()
        for fragment, category in CATEGORY_MAP.items():
            if fragment in lower:
                return category
    return "unknown"


def extract_features(payload: Dict[str, Any]) -> List[AnalysisFeature]:
    """
    Derive features from the final payload.

    Sources used:
      - payload["modules"]  → structural/architectural features (one feature per module)
      - payload["files"]    → enriches category via path inspection
      - payload["validation"] → validation quality as a meta-feature

    Confidence is taken directly from module.confidence; never fabricated.
    """
    features: List[AnalysisFeature] = []
    modules: List[Dict] = payload.get("modules", [])

    for idx, mod in enumerate(modules, start=1):
        mod_name: str = mod.get("name", "unnamed")
        mod_files: List[str] = mod.get("files", [])
        confidence: float = mod.get("confidence", 0.0)

        category = _infer_category(mod_files + [mod_name])

        features.append(AnalysisFeature(
            id=f"feat-{idx:03d}",
            name=_humanize_module_name(mod_name),
            confidence=round(confidence, 2),
            sources=mod_files,
            category=category,
        ))

    # Add a validation-quality meta-feature if score is present
    validation = payload.get("validation", {})
    val_score = validation.get("score", None)
    if val_score is not None:
        features.append(AnalysisFeature(
            id=f"feat-{len(features) + 1:03d}",
            name="Structural Validation Quality",
            confidence=round(float(val_score), 2),
            sources=["app/context/validator.py"],
            category="core_pipeline",
        ))

    return features


def _humanize_module_name(snake: str) -> str:
    """Convert snake_case module name to a Title Case feature name."""
    return " ".join(word.capitalize() for word in snake.replace("_", " ").split())


# ---------------------------------------------------------------------------
# Stage 2: Requirement derivation
# ---------------------------------------------------------------------------

def _source_modules_from_files(sources: List[str]) -> List[str]:
    """Extract unique top-level module directory names from file paths."""
    seen = set()
    result = []
    for path in sources:
        parts = path.replace("\\", "/").split("/")
        if len(parts) >= 2:
            mod = parts[0]  # top-level dir
        else:
            mod = "root"
        if mod not in seen:
            seen.add(mod)
            result.append(mod)
    return sorted(result)


def derive_requirements(features: List[AnalysisFeature]) -> List[Requirement]:
    """
    Derive one SHALL-style functional requirement per detected feature.

    Rules:
      - Each feature produces exactly one requirement (1:1 mapping)
      - Priority is derived from feature category via PRIORITY_MAP
      - Description is a SHALL statement constructed from the feature name
      - source_modules are inferred from feature.sources file paths
      - Low-confidence features (< 0.4) get priority downgraded to Low
    """
    requirements: List[Requirement] = []

    for feat in features:
        base_priority = PRIORITY_MAP.get(feat.category, "Low")

        # Downgrade priority for low-confidence detections
        if feat.confidence < 0.4 and base_priority == "High":
            priority = "Medium"
        elif feat.confidence < 0.2:
            priority = "Low"
        else:
            priority = base_priority

        description = (
            f"The system SHALL implement the '{feat.name}' capability "
            f"as evidenced by {len(feat.sources)} source file(s) "
            f"with a structural confidence of {feat.confidence}."
        )

        source_mods = _source_modules_from_files(feat.sources)
        if not source_mods:
            source_mods = ["unknown"]

        requirements.append(Requirement(
            id=f"REQ-{len(requirements) + 1:03d}",
            feature_id=feat.id,
            description=description,
            priority=priority,
            source_modules=source_mods,
        ))

    return requirements


# ---------------------------------------------------------------------------
# Stage 3: Minimal BRD assembly
# ---------------------------------------------------------------------------

def _derive_summary(repo_name: str, modules: List[Dict]) -> str:
    """Produce a one-line system summary from repo name and detected module names."""
    if not modules:
        return f"{repo_name}: A software repository with no detected structural modules."
    mod_names = [m.get("name", "") for m in modules if m.get("name")]
    if len(mod_names) <= 3:
        mod_str = ", ".join(mod_names)
    else:
        mod_str = f"{', '.join(mod_names[:3])}, and {len(mod_names) - 3} more"
    return (
        f"{repo_name}: A system comprising {len(modules)} structural module(s) "
        f"({mod_str})."
    )


def _derive_gaps(payload: Dict[str, Any]) -> List[str]:
    """
    Derive gaps strictly from validation issues in the payload.
    Does NOT invent gaps not present in the data.
    """
    return payload.get("validation", {}).get("issues", [])


def build_brd(payload: Dict[str, Any]) -> MinimalBRD:
    """
    Orchestrates the three conversion stages and returns a MinimalBRD.

    This function is the single public entry point for the PayloadConverter.
    It is deterministic: identical inputs produce identical outputs.
    """
    repo_name: str = payload.get("repo_name", "unknown")
    modules: List[Dict] = payload.get("modules", [])
    validation = payload.get("validation", {})

    features = extract_features(payload)
    requirements = derive_requirements(features)
    gaps = _derive_gaps(payload)
    summary = _derive_summary(repo_name, modules)

    return MinimalBRD(
        repo_name=repo_name,
        summary=summary,
        validation_score=round(float(validation.get("score", 0.0)), 2),
        validation_passed=bool(validation.get("valid", False)),
        features=features,
        requirements=requirements,
        gaps=gaps,
        modules_detected=[m.get("name", "") for m in modules],
    )


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="PayloadConverter: Convert final pipeline payload → Features + Requirements + Minimal BRD."
    )
    parser.add_argument(
        "--payload",
        default="runtime/outputs/final_payload.json",
        help="Path to the final pipeline payload JSON (default: runtime/outputs/final_payload.json)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional path to write the BRD JSON output (prints to stdout if omitted)",
    )
    args = parser.parse_args()

    payload_path = Path(args.payload)
    if not payload_path.exists():
        print(f"[ERROR] Payload file not found: {payload_path}")
        raise SystemExit(1)

    with open(payload_path, "r", encoding="utf-8") as fh:
        try:
            raw_payload = json.load(fh)
        except json.JSONDecodeError as exc:
            print(f"[ERROR] Invalid JSON in {payload_path}: {exc}")
            raise SystemExit(1)

    brd = build_brd(raw_payload)
    brd_json = brd.model_dump_json(indent=2)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(brd_json)
        print(f"[OK] BRD written to {out_path}")
    else:
        print(brd_json)

    # Summary stats to stderr so they don't pollute stdout JSON piping
    import sys
    print(
        f"\n[SUMMARY] repo={brd.repo_name} | "
        f"features={len(brd.features)} | "
        f"requirements={len(brd.requirements)} | "
        f"gaps={len(brd.gaps)} | "
        f"validation={'PASS' if brd.validation_passed else 'FAIL'} ({brd.validation_score})",
        file=sys.stderr,
    )
