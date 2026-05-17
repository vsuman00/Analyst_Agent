"""
product_understanding_agent.py — Layer 3 Tool
-----------------------------------------------
ProductUnderstandingAgent

Input:
  List of ValidatedFeature dicts (output of FeatureValidator):
  [
    {
      "id": str,
      "name": str,          # snake_case
      "description": str,
      "confidence": float,
      "merge_of": [str]
    }
  ]

Output (strict JSON):
  {
    "product": {
      "name": str,           # snake_case product label
      "summary": str,        # ≤ 120 words, template-driven, no fluff
      "core_capabilities": [str]  # title-case, one per high-confidence feature
    }
  }

Derivation logic (all rule-based, no LLM):

  PRODUCT NAME
    Derived by scanning feature names for DOMAIN_SIGNALS keyword sets.
    Each signal cluster votes for a product archetype.
    The archetype with the most votes wins; ties broken by total confidence sum.
    If no cluster has ≥ 2 signal hits → product name = "software_system" (safe fallback).

  SUMMARY
    Template: "{product_display_name} is a {archetype_description} comprising
    {N} functional capabilities including {top_3_capability_labels}."
    + optional sentence for infrastructure/testing if those features are present.
    Word count is hard-enforced to ≤ 120 words by truncating at sentence boundary.

  CORE CAPABILITIES
    All features with confidence ≥ CAPABILITY_THRESHOLD (default 0.7).
    Each snake_case name is converted to Title Case for display.
    Sorted: confidence desc, then name asc.

Strict rules:
  - No field is invented; every string is derived from input feature data.
  - No external assumptions, domain knowledge, or LLM calls.
  - If confidence threshold yields 0 capabilities → lower threshold to 0.5 and retry once.
  - summary is always ≤ 120 words (hard trim at sentence boundary if needed).

Usage (CLI):
  python -m app.analysis.product_understanding_agent \
    --features runtime/outputs/validated_features.json \
    [--out     runtime/outputs/product_understanding.json]
"""

from __future__ import annotations

import json
import argparse
import os
import sys
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any, Optional

from app.schemas.models import ProductProfile, ProductUnderstandingResult

# Attempt to load the LLM client (optional — falls back to keyword voting if absent)
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(dotenv_path=_env_path, override=False)
except ImportError:
    pass

try:
    from app.utils.llm_client import llm_json_call as _llm_json_call
except ImportError:
    _llm_json_call = None  # type: ignore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CAPABILITY_THRESHOLD: float = 0.7

# ---------------------------------------------------------------------------
# Archetype domain signals — loaded from app/analysis/config/archetype_registry.json
# To add a new archetype, edit that JSON file. Zero Python changes required.
# ---------------------------------------------------------------------------
from app.analysis.archetype_loader import get_domain_signals

# Infrastructure/testing feature name substrings — reported separately in summary
INFRA_SIGNALS: Set[str] = {"container", "ci_cd", "test", "deploy", "docker", "kubernetes"}
TEST_SIGNALS:  Set[str] = {"test", "spec", "assert"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Acronyms that must not be naive-title-cased
ACRONYM_MAP: Dict[str, str] = {
    "ci":     "CI",
    "cd":     "CD",
    "ci_cd":  "CI/CD",
    "grpc":   "gRPC",
    "rest":   "REST",
    "api":    "API",
    "sql":    "SQL",
    "db":     "DB",
    "jwt":    "JWT",
    "url":    "URL",
    "http":   "HTTP",
    "https":  "HTTPS",
    "etl":    "ETL",
    "rpc":    "RPC",
}


def _to_title(snake: str) -> str:
    """
    Convert snake_case to a human-readable label, preserving known acronyms.
    e.g. 'container_orchestration_ci_cd_config' →
         'Container Orchestration CI/CD Config'
    """
    # First handle multi-token acronyms that span underscores
    for multi_key, display in ACRONYM_MAP.items():
        if "_" in multi_key:
            snake = snake.replace(multi_key, display.replace("/", "_SLASH_"))

    words = []
    # Build a normalised lookup: UPPERCASED_NO_SLASH → display_form
    _upper_to_display: Dict[str, str] = {
        v.replace("/", "").upper(): v for v in ACRONYM_MAP.values()
    }
    for token in snake.split("_"):
        if token == "SLASH":
            # re-attach to previous word as /
            if words:
                words[-1] = words[-1] + "/"
            continue
        upper_tok = token.upper()
        if upper_tok in _upper_to_display:
            words.append(_upper_to_display[upper_tok])
        else:
            words.append(token.capitalize())


    # Re-join, collapsing any trailing slash artefacts
    result = " ".join(words)
    # Clean up "CI/ CD" artefact from multi-token replacement
    result = re.sub(r"(\w+)/\s+(\w+)", r"\1/\2", result)
    return result


def _word_count(text: str) -> int:
    return len(text.split())


def _trim_to_words(text: str, max_words: int) -> str:
    """
    Trim text to at most max_words words, cutting at the last sentence
    boundary ('. ') before the limit. Appends ellipsis only if trimmed.
    """
    words = text.split()
    if len(words) <= max_words:
        return text
    # Try sentence boundary
    candidate = " ".join(words[:max_words])
    last_period = candidate.rfind(". ")
    if last_period > 0:
        return candidate[: last_period + 1]
    # Hard cut
    return candidate.rstrip(",;:") + "."


# ---------------------------------------------------------------------------
# Step A — Detect product archetype from feature names (FALLBACK only)
# ---------------------------------------------------------------------------

def _detect_archetype(features: List[Dict]) -> Tuple[str, str, str]:
    """
    FALLBACK: Vote across archetype_registry.json clusters using feature names.
    Used only when LLM archetype detection is unavailable or fails.

    Returns (archetype_snake, archetype_display, fragment) for winner.
    Falls back to ("software_system", "Software System", "multi-capability software system")
    if no cluster scores >= 2 votes.
    """
    domain_signals = get_domain_signals()   # loaded from archetype_registry.json
    scores: Dict[str, Dict] = {k: {"votes": 0, "conf_sum": 0.0} for k in domain_signals}

    for feat in features:
        feat_name: str = feat["name"]       # already snake_case
        feat_conf: float = feat.get("confidence", 0.0)

        for cluster, spec in domain_signals.items():
            for kw in spec["keywords"]:
                if kw in feat_name:
                    scores[cluster]["votes"] += 1
                    scores[cluster]["conf_sum"] += feat_conf
                    break  # one vote per feature per cluster

    # Pick winner: most votes, tiebreak by conf_sum
    best_cluster = max(
        scores.items(),
        key=lambda kv: (kv[1]["votes"], kv[1]["conf_sum"]),
    )
    cluster_name, cluster_score = best_cluster

    if cluster_score["votes"] < 2:
        return (
            "software_system",
            "Software System",
            "multi-capability software system",
        )

    spec = domain_signals[cluster_name]
    return cluster_name, spec["display"], spec["fragment"]


# ---------------------------------------------------------------------------
# Step B — Derive core capabilities
# ---------------------------------------------------------------------------

def _derive_capabilities(
    features: List[Dict],
    threshold: float = CAPABILITY_THRESHOLD,
) -> List[str]:
    """
    Return Title Case capability labels for features at or above threshold,
    sorted by confidence desc then name asc.
    Falls back to threshold=0.5 if the primary threshold yields nothing.
    """
    high = [f for f in features if f.get("confidence", 0.0) >= threshold]

    if not high and threshold > 0.5:
        high = [f for f in features if f.get("confidence", 0.0) >= 0.5]

    high.sort(key=lambda f: (-f.get("confidence", 0.0), f.get("name", "")))
    return [_to_title(f["name"]) for f in high]


# ---------------------------------------------------------------------------
# Step C — Build summary (≤ 120 words, template-driven)
# ---------------------------------------------------------------------------

def _build_summary(
    archetype_display: str,
    fragment: str,
    features: List[Dict],
    capabilities: List[str],
) -> str:
    """
    Construct a template-driven summary using only feature-derived strings.

    Template:
      "{archetype_display} is a {fragment} comprising {N} functional
       capabilities: {top_3}[, and more].[ It includes infrastructure support
       for {infra_labels}.][  An automated test suite is present.]"
    """
    n_caps = len(capabilities)
    if n_caps == 0:
        top_label = "no high-confidence capabilities detected"
    elif n_caps <= 3:
        top_label = ", ".join(capabilities)
    else:
        top_label = ", ".join(capabilities[:3]) + f", and {n_caps - 3} more"

    # Core sentence
    parts: List[str] = [
        f"{archetype_display} is a {fragment} comprising "
        f"{n_caps} functional capability/capabilities: {top_label}."
    ]

    # Infrastructure addendum (only if infra features present and they're NOT the archetype)
    infra_feats = [
        _to_title(f["name"])
        for f in features
        if any(sig in f["name"] for sig in INFRA_SIGNALS)
        and f.get("confidence", 0.0) >= 0.7
    ]
    if infra_feats:
        infra_str = ", ".join(infra_feats[:2])
        parts.append(f"Infrastructure includes {infra_str}.")

    # Test suite addendum
    has_tests = any(
        any(sig in f["name"] for sig in TEST_SIGNALS)
        for f in features
        if f.get("confidence", 0.0) >= 0.7
    )
    if has_tests:
        parts.append("An automated test suite is present.")

    summary = " ".join(parts)
    return _trim_to_words(summary, 120)


# ---------------------------------------------------------------------------
# LLM Archetype Detection (PRIMARY PATH — dynamic, universal)
# ---------------------------------------------------------------------------

_ARCHETYPE_SYSTEM_PROMPT = """\
You are a senior product analyst. Given a list of software features, optional product documentation,
and a STRUCTURED EVIDENCE block, your task is to identify the PRODUCT ARCHETYPE of this application.

Rules:
- The STRUCTURED EVIDENCE block is the highest-priority signal. It reflects what files and configs
  were actually found in the repository. Trust it over inferred feature names.
- Infer the archetype from the features, documentation, and evidence ONLY. Do not make assumptions.
- Use a concise, specific archetype label (e.g. "AI-Powered Resume Analysis Tool", not "Software System").
- The product_name must be snake_case (e.g. "ai_resume_checker", "weather_dashboard").
- The summary must be <= 100 words in plain English, describing what the product does for its users.
- core_capabilities must be Title Case, user-facing feature names (not technical component names).
- If evidence shows has_android=true or has_ios=true → archetype MUST be "Mobile Application" or
  a specific mobile type (e.g. "Android Demo App"). NEVER classify as Web App or Server.
- If evidence shows has_desktop=true → classify as "Desktop Application".
- If evidence shows has_http_api=false and has_grpc=false → do NOT describe as an API backend.
- If has_kubernetes=false → do NOT mention Kubernetes or cloud-native infrastructure.
- If the repo is explicitly a demo/example → reflect that (e.g. "Android Demo App").

Return ONLY valid JSON:
{
  "product_name": "snake_case_identifier",
  "archetype_display": "Human-Readable Product Type",
  "core_capabilities": ["Feature One", "Feature Two", "Feature Three"],
  "summary": "Plain English summary of what the product does (<= 100 words)"
}
"""


def _llm_detect_archetype(
    validated_features: List[Dict],
    repo_context: Optional[Dict] = None,
    evidence: Optional[Dict] = None,
) -> Optional[Dict]:
    """
    PRIMARY: Use LLM to dynamically detect product archetype from features + README + evidence.
    Returns None on any failure so caller falls back to DOMAIN_SIGNALS keyword voting.
    """
    if not _llm_json_call or not os.environ.get("OPENAI_API_KEY"):
        return None

    feature_list = [
        {
            "name": f.get("name", ""),
            "description": f.get("description", ""),
            "confidence": f.get("confidence", 0.0),
        }
        for f in validated_features
    ]

    readme_excerpt = ""
    if repo_context:
        signals = repo_context.get("intent_signals", {})
        readme_excerpt = signals.get("readme", "")[:2000].strip()

    # Build structured evidence block — highest-priority signal for the LLM
    ev = evidence or {}
    evidence_block = {
        "platform":         ev.get("platform", "unknown"),
        "has_android":      ev.get("has_android", False),
        "has_ios":          ev.get("has_ios", False),
        "has_desktop":      ev.get("has_desktop", False),
        "has_http_api":     ev.get("has_http_api", False),
        "has_grpc":         ev.get("has_grpc", False),
        "has_kubernetes":   ev.get("has_kubernetes", False),
        "has_docker":       ev.get("has_docker", False),
        "has_database":     ev.get("has_database", False),
        "primary_language": ev.get("primary_language", "unknown"),
        "build_tool":       ev.get("build_tool", "unknown"),
        "api_endpoint_count": len(ev.get("actual_endpoints", [])),
    }

    user_prompt = (
        f"STRUCTURED EVIDENCE (highest priority — reflects actual repo files):\n"
        f"{json.dumps(evidence_block, indent=2)}\n\n"
        f"Product Documentation (secondary signal):\n{readme_excerpt or '[Not available]'}\n\n"
        f"Detected Features:\n{json.dumps(feature_list, indent=2)}\n\n"
        "Identify the product archetype and return the JSON response."
    )

    try:
        result = _llm_json_call(_ARCHETYPE_SYSTEM_PROMPT, user_prompt, max_tokens=500)
        if all(k in result for k in ["product_name", "archetype_display", "summary", "core_capabilities"]):
            print(f"[ProductUnderstanding] LLM archetype: '{result['archetype_display']}'")
            return result
        return None
    except Exception as e:
        print(f"[ProductUnderstanding] LLM archetype detection failed, using keyword fallback: {e}")
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def understand_product(
    validated_features: List[Dict],
    repo_context: Optional[Dict] = None,
    evidence: Optional[Dict] = None,
) -> ProductUnderstandingResult:
    """
    Derive a ProductProfile from validated feature data.

    PRIMARY PATH : LLM call for fully dynamic, universal archetype detection.
    FALLBACK PATH: DOMAIN_SIGNALS keyword voting (deterministic, no API key needed).

    Parameters
    ----------
    validated_features : list of ValidatedFeature dicts
    repo_context : optional RepoContext dict from RepoContextBuilder
    evidence : optional RepoEvidenceManifest dict (highest-priority platform signal)
    """
    if not validated_features:
        return ProductUnderstandingResult(
            product=ProductProfile(
                name="unknown_system",
                summary="No validated features provided. Product cannot be characterised.",
                core_capabilities=[],
            )
        )

    # ── PRIMARY: LLM dynamic archetype detection ─────────────────────────────
    llm_result = _llm_detect_archetype(validated_features, repo_context, evidence=evidence)
    if llm_result:
        summary = _trim_to_words(llm_result.get("summary", ""), 120)
        return ProductUnderstandingResult(
            product=ProductProfile(
                name=llm_result["product_name"],
                summary=summary,
                core_capabilities=llm_result.get("core_capabilities", []),
            )
        )

    # ── FALLBACK: Keyword voting ────────────────────────────────────────
    print("[ProductUnderstanding] Using DOMAIN_SIGNALS keyword voting fallback.")
    archetype_snake, archetype_display, fragment = _detect_archetype(validated_features)
    capabilities = _derive_capabilities(validated_features)
    summary = _build_summary(archetype_display, fragment, validated_features, capabilities)

    assert _word_count(summary) <= 120, (
        f"Summary exceeded 120 words ({_word_count(summary)}): {summary}"
    )

    return ProductUnderstandingResult(
        product=ProductProfile(
            name=archetype_snake,
            summary=summary,
            core_capabilities=capabilities,
        )
    )


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "ProductUnderstandingAgent: Derive product name, summary, and core "
            "capabilities purely from validated features. Returns JSON only."
        )
    )
    parser.add_argument(
        "--features",
        default="runtime/outputs/validated_features.json",
        help="Path to validated_features.json (default: runtime/outputs/validated_features.json)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional path to write output JSON (prints to stdout if omitted)",
    )
    args = parser.parse_args()

    feat_path = Path(args.features)
    if not feat_path.exists():
        print(f"[ERROR] File not found: {feat_path}", file=sys.stderr)
        raise SystemExit(1)

    with open(feat_path, encoding="utf-8") as fh:
        raw = json.load(fh)

    # Accept { "validated_features": [...] } or bare list
    feat_list: List[Dict] = (
        raw.get("validated_features", raw) if isinstance(raw, dict) else raw
    )

    result = understand_product(feat_list)
    output_json = result.model_dump_json(indent=2)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(output_json)
        print(f"[OK] Product understanding written to {out_path}", file=sys.stderr)
    else:
        print(output_json)

    p = result.product
    wc = _word_count(p.summary)
    print(
        f"\n[SUMMARY] product={p.name} | "
        f"capabilities={len(p.core_capabilities)} | "
        f"summary_words={wc}/120",
        file=sys.stderr,
    )
