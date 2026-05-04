"""
brd_validator.py — Layer 3 Tool
---------------------------------
BRDValidator

Validates a generated Markdown BRD against the pipeline inputs that produced it.

Inputs:
  - brd_markdown            : str  (raw Markdown content of the BRD)
  - features                : List[Dict]  (InterpretedFeature / ValidatedFeature)
  - functional_requirements : List[Dict]  (FunctionalRequirement)

Output (strict JSON):
  {
    "score": float,           # 0.0 – 1.0
    "issues": [str],          # Specific, actionable violation messages
    "needs_revision": bool    # True if score < 0.85
  }

Scoring Dimensions (equal weight, each 0.0–1.0, averaged):
  1. Traceability  — every feature name and every FR-ID referenced in inputs appears in the BRD
  2. Completeness  — all 8 required section headings are present
  3. Clarity       — no banned vague phrases found in the BRD text
  4. No-Hallucination — BRD contains no FR-IDs or feature names absent from the input sets

Rules:
  - Scoring is purely structural and lexical — no LLM inference
  - Every issue recorded is specific (includes the offending term or missing element)
  - score < 0.85 → needs_revision = True
"""

from __future__ import annotations

import json
import argparse
import sys
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple

from app.schemas.models import BRDValidationResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_SECTIONS = [
    "## 1. Executive Summary",
    "## 2. Business Context",
    "## 3. Current State Analysis",
    "## 4. Stakeholders",
    "## 5. Functional Requirements",
    "## 6. Non-Functional Requirements",
    "## 7. Data Requirements",
    "## 8. Technology Stack",
    "## 9. CI/CD Pipeline",
    "## 10. Infrastructure",
    "## 11. Risk Register",
    "## 12. Compliance",
    "## 13. Acceptance Criteria",
    "## 14. Delivery Roadmap",
    "## 15. Open Issues",
    "## 16. Document Approval",
]

BANNED_PHRASES = [
    "should be fast",
    "user-friendly",
    "easy to use",
    "seamlessly",
    "robust solution",
    "best-in-class",
    "leveraging synergies",
    "mission-critical",
    "world-class",
    "cutting-edge",
    "bleeding-edge",
    "state of the art",
    "scalable and reliable",
    "highly scalable",
    "highly reliable",
    "as needed",
    "and so on",
    "etc.",
]

FR_ID_PATTERN = re.compile(r'\bFR-\d+\b')
NFR_ID_PATTERN = re.compile(r'\bNFR-\d+\b')

REVISION_THRESHOLD = 0.85

# ---------------------------------------------------------------------------
# Dimension scorers
# ---------------------------------------------------------------------------

def _score_completeness(brd: str) -> Tuple[float, List[str]]:
    """Check that all 8 required section headings are present."""
    issues = []
    found = 0
    for heading in REQUIRED_SECTIONS:
        if heading in brd:
            found += 1
        else:
            issues.append(f"Missing required section: '{heading}'")
    score = found / len(REQUIRED_SECTIONS)
    return round(score, 4), issues


def _score_traceability(
    brd: str,
    features: List[Dict],
    frs: List[Dict]
) -> Tuple[float, List[str]]:
    """
    Check that every input feature name and every FR-ID appears in the BRD.
    Partial credit: ratio of traced items to total expected items.
    """
    issues = []
    total = 0
    found = 0

    # Feature names
    for feat in features:
        raw_name = feat.get("name", "")
        if not raw_name:
            continue
        display_name = raw_name.replace("_", " ").title()
        total += 1
        if raw_name in brd or display_name in brd:
            found += 1
        else:
            issues.append(
                f"Feature '{display_name}' from input is not referenced in the BRD."
            )

    # FR IDs
    for fr in frs:
        fr_id = fr.get("id", "")
        if not fr_id:
            continue
        total += 1
        if fr_id in brd:
            found += 1
        else:
            issues.append(
                f"Functional requirement '{fr_id}' from input is not referenced in the BRD."
            )

    score = (found / total) if total > 0 else 1.0
    return round(score, 4), issues


def _score_no_hallucination(
    brd: str,
    features: List[Dict],
    frs: List[Dict]
) -> Tuple[float, List[str]]:
    """
    Check that BRD does not contain FR-IDs absent from the input set.
    Feature name hallucination is harder to detect lexically; we focus on
    the structured identifiers (FR-N) as the primary hallucination vector.
    """
    issues = []

    # Build known FR-ID set
    known_fr_ids = {fr.get("id", "") for fr in frs if fr.get("id")}

    # Extract all FR-IDs mentioned in BRD
    brd_fr_ids = set(FR_ID_PATTERN.findall(brd))

    phantom_ids = brd_fr_ids - known_fr_ids
    if phantom_ids:
        for pid in sorted(phantom_ids):
            issues.append(
                f"BRD references '{pid}' which is NOT present in the input functional requirements. "
                "Potential hallucination."
            )
        score = max(0.0, 1.0 - (len(phantom_ids) / max(len(brd_fr_ids), 1)))
    else:
        score = 1.0

    return round(score, 4), issues


def _score_clarity(brd: str) -> Tuple[float, List[str]]:
    """
    Penalise presence of banned vague phrases.
    Each violation deducts a fixed 0.1 from a starting score of 1.0.
    Minimum score is 0.0.
    """
    issues = []
    brd_lower = brd.lower()
    for phrase in BANNED_PHRASES:
        if phrase in brd_lower:
            issues.append(
                f"Banned vague phrase found in BRD: \"{phrase}\". "
                "Replace with a specific, measurable statement."
            )

    score = max(0.0, 1.0 - len(issues) * 0.1)
    return round(score, 4), issues


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_brd(
    brd_markdown: str,
    features: List[Dict],
    functional_requirements: List[Dict],
) -> BRDValidationResult:
    """
    Run all four scoring dimensions and return an aggregated result.
    """
    all_issues: List[str] = []

    completeness_score,    completeness_issues    = _score_completeness(brd_markdown)
    traceability_score,    traceability_issues    = _score_traceability(brd_markdown, features, functional_requirements)
    no_halluc_score,       no_halluc_issues       = _score_no_hallucination(brd_markdown, features, functional_requirements)
    clarity_score,         clarity_issues         = _score_clarity(brd_markdown)

    all_issues.extend(completeness_issues)
    all_issues.extend(traceability_issues)
    all_issues.extend(no_halluc_issues)
    all_issues.extend(clarity_issues)

    # Equal-weight average across all four dimensions
    aggregate_score = round(
        (completeness_score + traceability_score + no_halluc_score + clarity_score) / 4,
        4
    )

    return BRDValidationResult(
        score=aggregate_score,
        issues=all_issues,
        needs_revision=aggregate_score < REVISION_THRESHOLD,
    )


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BRDValidator: Validate a generated BRD.")
    parser.add_argument("--brd",          required=True, help="Path to BRD Markdown file")
    parser.add_argument("--features",     required=True, help="Path to features JSON")
    parser.add_argument("--requirements", required=True, help="Path to functional_requirements JSON")
    parser.add_argument("--out",          default=None,  help="Output JSON path (prints to stdout if omitted)")
    args = parser.parse_args()

    brd_path = Path(args.brd)
    if not brd_path.exists():
        print(f"[ERROR] BRD file not found: {brd_path}", file=sys.stderr)
        sys.exit(1)
    brd_text = brd_path.read_text(encoding="utf-8")

    def _load_json(path_str: str) -> Any:
        p = Path(path_str)
        if not p.exists():
            print(f"[ERROR] File not found: {p}", file=sys.stderr)
            sys.exit(1)
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    raw_feat = _load_json(args.features)
    feat_list: List[Dict] = (
        raw_feat.get("features", raw_feat.get("validated_features", []))
        if isinstance(raw_feat, dict) else raw_feat
    )

    raw_fr = _load_json(args.requirements)
    fr_list: List[Dict] = (
        raw_fr.get("functional_requirements", [])
        if isinstance(raw_fr, dict) else raw_fr
    )

    result = validate_brd(brd_text, feat_list, fr_list)
    output_json = result.model_dump_json(indent=2)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_json, encoding="utf-8")
        print(f"[OK] Validation result written to {out_path}", file=sys.stderr)
    else:
        print(output_json)

    # Human-readable summary on stderr
    verdict = "REVISION REQUIRED" if result.needs_revision else "PASSED"
    print(
        f"\n[RESULT] score={result.score:.2%} | issues={len(result.issues)} | verdict={verdict}",
        file=sys.stderr,
    )
