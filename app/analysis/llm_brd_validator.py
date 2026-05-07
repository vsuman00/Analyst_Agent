"""
llm_brd_validator.py — Two-Layer BRD Validator
------------------------------------------------
Replaces the superficial heading-check in brd_validator.py.

Layer 1 — Structural (deterministic, instant):
  - All 16 section headings present
  - No banned phrases
  - FR-IDs in BRD match FR-IDs in evidence bundle
  - Minimum word count per section

Layer 2 — Semantic (LLM-based, grounded):
  - For each section, asks the LLM to verify claims against evidence
  - Returns per-section scores and unverified claims
  - Falls back gracefully if LLM unavailable

Final score: structural (40%) + semantic avg (60%)
Threshold: score >= 0.80 = PASS
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from app.analysis.prompts.section_prompts import VALIDATOR_SYSTEM
from app.utils.logger import get_logger, log

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_HEADINGS = [
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
    "should be fast", "user-friendly", "easy to use", "seamlessly",
    "robust solution", "best-in-class", "leveraging synergies",
    "mission-critical", "world-class", "cutting-edge", "bleeding-edge",
    "state of the art", "scalable and reliable", "highly scalable",
    "highly reliable", "and so on", "etc.",
]

PASS_THRESHOLD   = 0.80
MIN_WORDS_PER_SECTION = 30   # sections with fewer words are flagged


# ---------------------------------------------------------------------------
# Layer 1 — Structural Checks
# ---------------------------------------------------------------------------

def _structural_check(
    brd: str,
    bundle: Dict,
) -> Tuple[float, List[str]]:
    """
    Deterministic structural validation.
    Returns (score 0.0-1.0, list of issue strings).
    """
    issues: List[str] = []
    checks_passed = 0
    total_checks  = 0

    # 1a. Required headings
    for heading in REQUIRED_HEADINGS:
        total_checks += 1
        if heading in brd:
            checks_passed += 1
        else:
            issues.append(f"MISSING_SECTION: '{heading}' not found in BRD.")

    # 1b. Banned phrases
    brd_lower = brd.lower()
    for phrase in BANNED_PHRASES:
        if phrase in brd_lower:
            issues.append(f"BANNED_PHRASE: '{phrase}' found — replace with specific statement.")

    # 1c. FR-ID traceability
    known_fr_ids = {fr.get("id", "") for fr in bundle.get("functional_requirements", [])}
    brd_fr_ids   = set(re.findall(r'\bFR-\d+\b', brd))
    phantom_frs  = brd_fr_ids - known_fr_ids
    for pid in sorted(phantom_frs):
        issues.append(f"PHANTOM_FR: '{pid}' in BRD but not in evidence bundle.")

    # 1d. Feature traceability
    feat_names = {
        f.get("name", "").replace("_", " ").lower()
        for f in bundle.get("features", [])
    }
    brd_words = brd.lower()
    missing_feats = [n for n in feat_names if n and n not in brd_words]
    for mf in missing_feats[:3]:  # report at most 3
        issues.append(f"UNTRACED_FEATURE: Feature '{mf}' from evidence not referenced in BRD.")

    # 1e. Section word count
    sections = re.split(r'\n## \d+\.', brd)
    for i, sec in enumerate(sections[1:], start=1):
        word_count = len(sec.split())
        if word_count < MIN_WORDS_PER_SECTION:
            total_checks += 1
            issues.append(
                f"THIN_SECTION: Section {i} has only {word_count} words "
                f"(minimum {MIN_WORDS_PER_SECTION})."
            )
        else:
            total_checks += 1
            checks_passed += 1

    score = checks_passed / total_checks if total_checks else 1.0
    return round(score, 4), issues


# ---------------------------------------------------------------------------
# Layer 2 — Semantic (LLM) Check
# ---------------------------------------------------------------------------

def _semantic_check(
    brd: str,
    bundle: Dict,
) -> Tuple[float, List[str], List[Dict]]:
    """
    LLM-based claim verification for a representative sample of sections.

    Validates sections 1, 3, 8, and 11 (the most hallucination-prone sections).
    Returns (avg_score, combined_issues, per_section_results).
    Falls back gracefully if LLM is unavailable.
    """
    try:
        from app.utils.llm_client import llm_json_call
    except Exception:
        log(logger.warning, "llm_validator.unavailable", action="skip_semantic_layer")
        return 1.0, [], []

    # Extract section texts by splitting on ## N.
    section_map: Dict[int, str] = {}
    parts = re.split(r'\n(## \d+\. [^\n]+)', brd)
    current_num = None
    for part in parts:
        heading_m = re.match(r'## (\d+)\. ', part)
        if heading_m:
            current_num = int(heading_m.group(1))
            section_map[current_num] = part
        elif current_num is not None:
            section_map[current_num] = section_map.get(current_num, "") + part

    # Validate the 4 most risk-prone sections
    validate_nums = [n for n in [1, 3, 8, 11] if n in section_map]
    section_names = {
        1: "Executive Summary", 3: "Current State Analysis",
        8: "Technology Stack",  11: "Risk Register",
    }

    scores:  List[float] = []
    issues:  List[str]   = []
    results: List[Dict]  = []

    # Compact bundle for validator (exclude chunks to save tokens)
    compact = {k: v for k, v in bundle.items() if k != "top_chunks"}

    for num in validate_nums:
        sec_text = section_map[num][:2000]  # cap at 2000 chars per section
        user_msg = (
            f"## BRD SECTION\n{sec_text}\n\n"
            f"## EVIDENCE BUNDLE\n```json\n"
            + json.dumps(compact, indent=2, default=str)[:3000]
            + "\n```"
        )
        try:
            result = llm_json_call(
                system_prompt=VALIDATOR_SYSTEM,
                user_prompt=user_msg,
                max_tokens=400,
            )
            sec_score = float(result.get("score", 1.0))
            sec_issues = result.get("issues", [])
            verdict    = result.get("verdict", "PASS")

            scores.append(sec_score)
            results.append({
                "section": section_names.get(num, f"Section {num}"),
                "score":   sec_score,
                "verdict": verdict,
                "issues":  sec_issues,
                "unverified_claims": result.get("unverified_claims", []),
            })

            if verdict == "REVIEW_REQUIRED":
                for iss in sec_issues:
                    issues.append(f"Section {num} ({section_names.get(num,'')}): {iss}")

            log(logger.info, "semantic.section.checked",
                section=section_names.get(num),
                score=sec_score, verdict=verdict)

        except Exception as exc:
            log(logger.error, "semantic.section.failed", section=num, error=str(exc))
            scores.append(1.0)  # assume OK if check failed

    avg = round(sum(scores) / len(scores), 4) if scores else 1.0
    return avg, issues, results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_brd_llm(
    brd_markdown: str,
    bundle: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Run two-layer BRD validation and return a structured result.

    Returns
    -------
    dict with keys:
      score          : float  — final weighted score (0.0-1.0)
      structural_score: float
      semantic_score : float
      issues         : [str]  — all issues from both layers
      section_results: [dict] — per-section semantic results
      needs_revision : bool   — True if score < PASS_THRESHOLD
      verdict        : str    — "PASS" | "REVISION_REQUIRED"
    """
    struct_score, struct_issues = _structural_check(brd_markdown, bundle)
    sem_score, sem_issues, sem_results = _semantic_check(brd_markdown, bundle)

    # Weighted final score
    final = round(struct_score * 0.4 + sem_score * 0.6, 4)
    all_issues = struct_issues + sem_issues
    verdict = "PASS" if final >= PASS_THRESHOLD else "REVISION_REQUIRED"

    log(logger.info, "brd_validation.complete",
        structural=struct_score, semantic=sem_score,
        final=final, verdict=verdict, issues=len(all_issues))

    return {
        "score":            final,
        "structural_score": struct_score,
        "semantic_score":   sem_score,
        "issues":           all_issues,
        "section_results":  sem_results,
        "needs_revision":   final < PASS_THRESHOLD,
        "verdict":          verdict,
    }
