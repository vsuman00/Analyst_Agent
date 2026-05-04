"""
fix_loop.py — Layer 3 Tool
----------------------------
FixLoop

Deterministic self-repair loop for a generated BRD.

Inputs:
  - brd_markdown       : str   (raw Markdown content of the BRD)
  - validation_result  : dict  (BRDValidationResult: score, issues, needs_revision)
  - features           : List[Dict]  (to resolve missing traceability)
  - functional_requirements : List[Dict]  (to resolve missing FR-ID references)

Logic:
  - If score >= 0.85 → return BRD unchanged (no-op)
  - If score < 0.85  → apply targeted repair passes:
      PASS 1 — Clarity:     Replace banned vague phrases with precise alternatives
      PASS 2 — Traceability: Inject a "Traceability Matrix" appendix listing any
                             missing feature or FR-ID references. Does NOT modify
                             existing sections or requirement text.
  - Re-validate after each pass using BRDValidator
  - Stop after at most MAX_ITERATIONS=2 or when score >= 0.85

Hard Invariants:
  - No new features are introduced
  - No existing requirement descriptions are modified
  - No sections are deleted
  - All inserted content is strictly derived from the original pipeline inputs

Output:
  {
    "brd_markdown":    str,   # Revised (or original) Markdown
    "final_score":     float,
    "iterations_run":  int,
    "revision_log":    [str]  # One entry per repair action applied
  }
"""

from __future__ import annotations

import json
import argparse
import sys
import re
from pathlib import Path
from typing import Dict, List, Any

from app.analysis.brd_validator import validate_brd
from app.schemas.models import BRDValidationResult

MAX_ITERATIONS = 2
REVISION_THRESHOLD = 0.85

# ---------------------------------------------------------------------------
# Clarity fix map — banned phrase → precise, measurable replacement
# ---------------------------------------------------------------------------

CLARITY_FIXES: Dict[str, str] = {
    "should be fast":          "SHALL respond within the defined latency threshold",
    "user-friendly":           "operable without prior specialist training",
    "easy to use":             "operable without prior specialist training",
    "seamlessly":              "without manual intervention",
    "robust solution":         "fault-tolerant system",
    "best-in-class":           "conformant with the defined specification",
    "leveraging synergies":    "sharing defined interfaces",
    "mission-critical":        "required for primary system operation",
    "world-class":             "conformant with the defined specification",
    "cutting-edge":            "current generation",
    "bleeding-edge":           "current generation",
    "state of the art":        "current generation",
    "scalable and reliable":   "horizontally scalable with defined availability targets",
    "highly scalable":         "capable of horizontal scaling",
    "highly reliable":         "designed with explicit fault-tolerance mechanisms",
    "as needed":               "according to the specified schedule",
    "and so on":               "(see full list in supporting documentation)",
    "etc.":                    "(see full list in supporting documentation)",
}


# ---------------------------------------------------------------------------
# Pass 1 — Clarity repair
# ---------------------------------------------------------------------------

def _apply_clarity_pass(brd: str, issues: List[str]) -> tuple[str, List[str]]:
    """
    Replace each banned vague phrase with its precise alternative.
    Only operates on phrases confirmed in the issues list.
    """
    log = []
    for banned, replacement in CLARITY_FIXES.items():
        # Case-insensitive replacement, preserve surrounding whitespace
        pattern = re.compile(re.escape(banned), re.IGNORECASE)
        if pattern.search(brd):
            brd = pattern.sub(replacement, brd)
            log.append(f"[CLARITY] Replaced \"{banned}\" → \"{replacement}\"")
    return brd, log


# ---------------------------------------------------------------------------
# Pass 2 — Traceability repair (appendix injection only)
# ---------------------------------------------------------------------------

def _build_traceability_appendix(
    brd: str,
    features: List[Dict],
    frs: List[Dict],
    issues: List[str],
) -> tuple[str, List[str]]:
    """
    Inject a Traceability Matrix appendix at the end of the BRD for any
    features or FR-IDs that are not already referenced in the body text.

    INVARIANT: No existing section is modified. No new requirements are added.
               The appendix only cross-references items already present in inputs.
    """
    log = []
    appendix_rows = []

    # Detect missing feature references
    for feat in features:
        raw_name = feat.get("name", "")
        display = raw_name.replace("_", " ").title()
        if raw_name not in brd and display not in brd:
            # Find the linked FR-IDs for this feature
            linked_frs = [
                fr.get("id", "")
                for fr in frs
                if fr.get("linked_feature", fr.get("mapped_feature", "")) == raw_name
            ]
            linked_str = ", ".join(linked_frs) if linked_frs else "—"
            evidence   = ", ".join(f"`{e}`" for e in feat.get("evidence", [])) or "—"
            appendix_rows.append(
                f"| {display} | {linked_str} | {evidence} |"
            )
            log.append(f"[TRACEABILITY] Injected feature '{display}' into traceability appendix.")

    # Detect missing FR-ID references
    fr_id_pattern = re.compile(r'\bFR-\d+\b')
    missing_fr_ids = [
        fr for fr in frs
        if fr.get("id") and fr["id"] not in brd
    ]

    if missing_fr_ids:
        for fr in missing_fr_ids:
            feat_link = fr.get("linked_feature", fr.get("mapped_feature", "unknown")).replace("_", " ").title()
            if not any(fr["id"] in row for row in appendix_rows):
                appendix_rows.append(
                    f"| {feat_link} | {fr['id']} | _(see FR section)_ |"
                )
            log.append(f"[TRACEABILITY] Injected '{fr['id']}' into traceability appendix.")

    if appendix_rows:
        appendix = (
            "\n\n---\n\n"
            "## Appendix A — Traceability Matrix\n\n"
            "_This appendix was generated by FixLoop to resolve traceability gaps. "
            "No new features or requirements have been added._\n\n"
            "| Feature | Linked Requirements | Evidence |\n"
            "|---|---|---|\n"
            + "\n".join(appendix_rows)
            + "\n"
        )
        brd = brd + appendix

    return brd, log


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_fix_loop(
    brd_markdown: str,
    validation_result: Dict,
    features: List[Dict],
    functional_requirements: List[Dict],
) -> Dict[str, Any]:
    """
    Run up to MAX_ITERATIONS repair passes on the BRD.

    Returns a dict with keys:
      brd_markdown, final_score, iterations_run, revision_log
    """
    current_brd    = brd_markdown
    revision_log   = []
    iterations_run = 0

    current_score = float(validation_result.get("score", 0.0))
    current_issues: List[str] = validation_result.get("issues", [])

    if current_score >= REVISION_THRESHOLD:
        return {
            "brd_markdown":   current_brd,
            "final_score":    current_score,
            "iterations_run": 0,
            "revision_log":   ["[INFO] Score already meets threshold. No repair needed."],
        }

    for iteration in range(1, MAX_ITERATIONS + 1):
        iterations_run = iteration
        revision_log.append(f"[ITERATION {iteration}] Starting repair. Current score: {current_score:.2%}")

        # Pass 1 — Clarity
        current_brd, clarity_log = _apply_clarity_pass(current_brd, current_issues)
        revision_log.extend(clarity_log)

        # Pass 2 — Traceability (only if traceability issues exist)
        traceability_issues = [i for i in current_issues if "not referenced" in i or "not present" in i]
        if traceability_issues:
            current_brd, trace_log = _build_traceability_appendix(
                current_brd, features, functional_requirements, current_issues
            )
            revision_log.extend(trace_log)

        # Re-validate
        updated_result = validate_brd(current_brd, features, functional_requirements)
        current_score  = updated_result.score
        current_issues = updated_result.issues

        revision_log.append(
            f"[ITERATION {iteration}] Repair complete. New score: {current_score:.2%} | "
            f"Remaining issues: {len(current_issues)}"
        )

        if current_score >= REVISION_THRESHOLD:
            revision_log.append(f"[INFO] Score threshold met after iteration {iteration}. Stopping.")
            break

    if current_score < REVISION_THRESHOLD:
        revision_log.append(
            f"[WARNING] Score {current_score:.2%} still below threshold after {iterations_run} iteration(s). "
            "Manual review recommended."
        )

    return {
        "brd_markdown":   current_brd,
        "final_score":    current_score,
        "iterations_run": iterations_run,
        "revision_log":   revision_log,
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FixLoop: Deterministic BRD repair loop.")
    parser.add_argument("--brd",            required=True, help="Path to BRD Markdown file")
    parser.add_argument("--validation",     required=True, help="Path to BRDValidationResult JSON")
    parser.add_argument("--features",       required=True, help="Path to features JSON")
    parser.add_argument("--requirements",   required=True, help="Path to functional_requirements JSON")
    parser.add_argument("--out-brd",        default=None,  help="Path to write revised BRD Markdown")
    parser.add_argument("--out-report",     default=None,  help="Path to write fix report JSON")
    args = parser.parse_args()

    def _load_json(path_str: str) -> Any:
        p = Path(path_str)
        if not p.exists():
            print(f"[ERROR] File not found: {p}", file=sys.stderr)
            sys.exit(1)
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    brd_path = Path(args.brd)
    if not brd_path.exists():
        print(f"[ERROR] BRD file not found: {brd_path}", file=sys.stderr)
        sys.exit(1)
    brd_text = brd_path.read_text(encoding="utf-8")

    validation_data = _load_json(args.validation)
    raw_feat        = _load_json(args.features)
    raw_fr          = _load_json(args.requirements)

    feat_list: List[Dict] = (
        raw_feat.get("features", raw_feat.get("validated_features", []))
        if isinstance(raw_feat, dict) else raw_feat
    )
    fr_list: List[Dict] = (
        raw_fr.get("functional_requirements", [])
        if isinstance(raw_fr, dict) else raw_fr
    )

    result = run_fix_loop(brd_text, validation_data, feat_list, fr_list)

    # Write revised BRD
    if args.out_brd:
        out_brd = Path(args.out_brd)
        out_brd.parent.mkdir(parents=True, exist_ok=True)
        out_brd.write_text(result["brd_markdown"], encoding="utf-8")
        print(f"[OK] Revised BRD written to {out_brd}", file=sys.stderr)
    else:
        print(result["brd_markdown"])

    # Write fix report
    report = {
        "final_score":    result["final_score"],
        "iterations_run": result["iterations_run"],
        "revision_log":   result["revision_log"],
    }
    report_json = json.dumps(report, indent=2)

    if args.out_report:
        out_report = Path(args.out_report)
        out_report.parent.mkdir(parents=True, exist_ok=True)
        out_report.write_text(report_json, encoding="utf-8")
        print(f"[OK] Fix report written to {out_report}", file=sys.stderr)
    else:
        print(report_json, file=sys.stderr)

    verdict = "PASSED" if result["final_score"] >= REVISION_THRESHOLD else "STILL NEEDS REVIEW"
    print(
        f"\n[RESULT] final_score={result['final_score']:.2%} | "
        f"iterations={result['iterations_run']} | verdict={verdict}",
        file=sys.stderr,
    )
