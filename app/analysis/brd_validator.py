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
# NEW: Deep Quality Checks
# ---------------------------------------------------------------------------

# Verbs that indicate a testable FR (SHALL-style language)
_TESTABLE_VERBS = re.compile(
    r'\b(shall|must|will|ensures?|validates?|rejects?|returns?|generates?|creates?|'
    r'authenticates?|authorizes?|logs?|records?|exposes?|accepts?|routes?)\b',
    re.IGNORECASE,
)

# Patterns indicating placeholder / unfinished NFR targets
_PLACEHOLDER_SLA_RE = re.compile(
    r'\b(strict|tbd|to be defined|to be determined|n/a|unspecified|pending)\b',
    re.IGNORECASE,
)

# Generic stakeholder names that indicate no real inference
_GENERIC_STAKEHOLDERS = {"end user", "end users", "admin", "administrator", "user", "users"}


def _score_fr_testability(brd: str) -> Tuple[float, List[str]]:
    """
    Check that FR descriptions contain testable verbs (SHALL, MUST, validates, etc.).
    Scans all lines containing FR-N identifiers.
    """
    issues = []
    fr_lines = [line for line in brd.split("\n") if FR_ID_PATTERN.search(line)]
    if not fr_lines:
        return 1.0, []

    testable_count = 0
    for line in fr_lines:
        if _TESTABLE_VERBS.search(line):
            testable_count += 1
        else:
            fr_id_match = FR_ID_PATTERN.search(line)
            if fr_id_match:
                issues.append(
                    f"{fr_id_match.group()} does not contain a testable verb "
                    "(SHALL, MUST, validates, returns, etc.). Requirement may not be verifiable."
                )

    score = testable_count / len(fr_lines) if fr_lines else 1.0
    return round(score, 4), issues


def _score_nfr_specificity(brd: str) -> Tuple[float, List[str]]:
    """
    Check that NFR SLA targets contain actual measurable values,
    not placeholders like 'Strict', 'TBD', or 'N/A'.
    """
    issues = []
    nfr_lines = [line for line in brd.split("\n") if NFR_ID_PATTERN.search(line)]
    if not nfr_lines:
        return 1.0, []

    placeholder_count = 0
    for line in nfr_lines:
        if _PLACEHOLDER_SLA_RE.search(line):
            nfr_id_match = NFR_ID_PATTERN.search(line)
            nfr_id = nfr_id_match.group() if nfr_id_match else "NFR-?"
            issues.append(
                f"{nfr_id} contains a placeholder SLA target ('Strict', 'TBD', etc.). "
                "Replace with a measurable value (e.g., '99.9% uptime', 'p99 < 200ms')."
            )
            placeholder_count += 1

    score = max(0.0, 1.0 - (placeholder_count / max(len(nfr_lines), 1)))
    return round(score, 4), issues


def _score_stakeholder_specificity(brd: str) -> Tuple[float, List[str]]:
    """
    Check that the Stakeholders section contains project-specific roles,
    not just generic 'End User' or 'Admin'.
    """
    issues = []

    # Extract stakeholder section content
    stakeholder_start = brd.find("## 4. Stakeholders")
    if stakeholder_start < 0:
        return 1.0, []  # Section missing — scored separately by completeness

    # Find the next section boundary
    next_section = brd.find("\n## ", stakeholder_start + 10)
    section_text = brd[stakeholder_start:next_section] if next_section > 0 else brd[stakeholder_start:]
    section_lower = section_text.lower()

    # Count how many table rows exist (lines starting with |)
    table_rows = [line for line in section_text.split("\n")
                  if line.strip().startswith("|") and "---" not in line and "Role" not in line]

    if not table_rows:
        issues.append("Stakeholder section contains no stakeholder entries.")
        return 0.5, issues

    # Check if ALL roles are generic
    generic_only = True
    for row in table_rows:
        row_lower = row.lower()
        cells = [c.strip().lower() for c in row_lower.split("|") if c.strip()]
        if cells:
            role = cells[0]
            if role not in _GENERIC_STAKEHOLDERS:
                generic_only = False
                break

    if generic_only:
        issues.append(
            "Stakeholder section contains only generic roles ('End User', 'Admin'). "
            "Stakeholders should be project-specific (e.g., 'Billing Manager', 'Security Officer')."
        )
        return 0.6, issues

    return 1.0, issues


def _score_section_depth(brd: str) -> Tuple[float, List[str]]:
    """
    Check that each required section has meaningful content (≥ 30 words).
    Also checks that the Executive Summary has ≥ 60 words.
    """
    issues = []
    sections_checked = 0
    sections_adequate = 0

    for i, heading in enumerate(REQUIRED_SECTIONS):
        start = brd.find(heading)
        if start < 0:
            continue  # Missing section — scored by completeness

        # Find the end of this section (next heading or EOF)
        end = len(brd)
        for next_heading in REQUIRED_SECTIONS[i + 1:]:
            next_pos = brd.find(next_heading)
            if next_pos > start:
                end = next_pos
                break

        section_body = brd[start + len(heading):end].strip()
        word_count = len(section_body.split())

        sections_checked += 1

        # Executive Summary gets a higher bar
        if "Executive Summary" in heading:
            if word_count < 60:
                issues.append(
                    f"Executive Summary is too shallow ({word_count} words). "
                    "Should be ≥ 60 words with project-specific content."
                )
            else:
                sections_adequate += 1
        else:
            if word_count < 30:
                short_name = heading.replace("## ", "")
                issues.append(
                    f"Section '{short_name}' has insufficient content ({word_count} words). "
                    "Should be ≥ 30 words."
                )
            else:
                sections_adequate += 1

    score = sections_adequate / max(sections_checked, 1)
    return round(score, 4), issues


# ---------------------------------------------------------------------------
# Dimension 9: Tech Grounding (evidence-aware)
# ---------------------------------------------------------------------------

# Terms whose presence in the BRD must be grounded by actual repo evidence
_TECH_GROUNDING_CHECKS = [
    # (brd_term,           evidence_key,        evidence_must_be_true)
    ("Kubernetes",         "has_kubernetes",     True),
    ("k8s",               "has_kubernetes",     True),
    ("Docker",            "has_docker",         True),
    ("Dockerfile",        "has_docker",         True),
    ("GDPR",              "has_gdpr_mention",   True),
    ("CCPA",              "has_gdpr_mention",   True),
    ("REST API",          "has_http_api",       True),
    ("RESTful",           "has_http_api",       True),
    ("gRPC",              "has_grpc",           True),
    ("Android",           "has_android",        True),
    ("Google Play",       "has_android",        True),
    ("App Store",         "has_ios",            True),
    ("iOS",               "has_ios",            True),
]


def _score_tech_grounding(
    brd: str,
    evidence: Dict,
) -> Tuple[float, List[str]]:
    """
    Dimension 9: Verify that technology claims in the BRD are grounded in the
    RepoEvidenceManifest. Checks for phantom tech mentions (e.g., Kubernetes
    written in the BRD when no k8s manifests exist in the repo).

    Returns a score of 1.0 if all claims are grounded (or no evidence dict
    provided). Deducts proportionally for each phantom claim found.
    """
    if not evidence:
        return 1.0, []  # no evidence dict → cannot check, pass through

    issues = []
    total_checks = 0
    failed = 0

    for brd_term, ev_key, required_true in _TECH_GROUNDING_CHECKS:
        # Use word boundary search (with optional plural 's') to avoid substring false positives (e.g. 'iOS' in 'scenarios')
        pattern = re.compile(r'\b' + re.escape(brd_term) + r's?\b', re.IGNORECASE)
        if not pattern.search(brd):
            continue
        total_checks += 1
        actual = bool(evidence.get(ev_key, False))
        if required_true and not actual:
            issues.append(
                f"[GROUNDING] BRD mentions '{brd_term}' but evidence key '{ev_key}' is False. "
                "This claim may not be supported by the repository."
            )
            failed += 1

    if total_checks == 0:
        return 1.0, []

    score = round(1.0 - (failed / total_checks), 4)
    return score, issues


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_brd(
    brd_markdown: str,
    features: List[Dict],
    functional_requirements: List[Dict],
    evidence: Dict = None,
) -> BRDValidationResult:
    """
    Run all scoring dimensions and return an aggregated result.

    Dimensions (9 total, equal weight):
      1. Completeness         — all required section headings present
      2. Traceability         — every input feature/FR referenced in the BRD
      3. No-Hallucination     — no phantom FR-IDs in the BRD
      4. Clarity              — no banned vague phrases
      5. FR Testability       — FRs contain testable verbs (SHALL, MUST, etc.)
      6. NFR Specificity      — NFR SLAs have real values, not 'Strict'/'TBD'
      7. Stakeholder Specificity — roles are project-specific, not generic
      8. Section Depth        — every section has meaningful content (word count)
      9. Tech Grounding       — BRD tech claims backed by evidence manifest
    """
    evidence = evidence or {}
    all_issues: List[str] = []

    # Dimensions 1–8 (structural)
    completeness_score,    completeness_issues    = _score_completeness(brd_markdown)
    traceability_score,    traceability_issues    = _score_traceability(brd_markdown, features, functional_requirements)
    no_halluc_score,       no_halluc_issues       = _score_no_hallucination(brd_markdown, features, functional_requirements)
    clarity_score,         clarity_issues         = _score_clarity(brd_markdown)
    fr_test_score,         fr_test_issues         = _score_fr_testability(brd_markdown)
    nfr_spec_score,        nfr_spec_issues        = _score_nfr_specificity(brd_markdown)
    stakeholder_score,     stakeholder_issues     = _score_stakeholder_specificity(brd_markdown)
    depth_score,           depth_issues           = _score_section_depth(brd_markdown)

    # Dimension 9 (evidence-aware)
    grounding_score,       grounding_issues       = _score_tech_grounding(brd_markdown, evidence)

    all_issues.extend(completeness_issues)
    all_issues.extend(traceability_issues)
    all_issues.extend(no_halluc_issues)
    all_issues.extend(clarity_issues)
    all_issues.extend(fr_test_issues)
    all_issues.extend(nfr_spec_issues)
    all_issues.extend(stakeholder_issues)
    all_issues.extend(depth_issues)
    all_issues.extend(grounding_issues)

    # Equal-weight average across all 9 dimensions
    aggregate_score = round(
        (
            completeness_score + traceability_score + no_halluc_score + clarity_score
            + fr_test_score + nfr_spec_score + stakeholder_score + depth_score
            + grounding_score
        ) / 9,
        4
    )

    # Force a revision if there are any grounding failures or requirement hallucinations,
    # ensuring the pipeline enters the self-annealing fix loop.
    needs_revision = (
        (aggregate_score < REVISION_THRESHOLD)
        or (grounding_score < 1.0)
        or (no_halluc_score < 1.0)
    )

    return BRDValidationResult(
        score=aggregate_score,
        issues=all_issues,
        needs_revision=needs_revision,
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
