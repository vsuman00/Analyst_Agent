"""
brd_composer.py — Layer 3 Tool
--------------------------------
BRDComposer (Enterprise Level)

Inputs:
  - business_context            : Dict (BusinessUnderstandingResult.business_context)
  - features                    : List[Dict] (InterpretedFeature / ValidatedFeature list)
  - functional_requirements     : List[Dict] (FunctionalRequirement list)
  - non_functional_requirements : List[Dict] (NonFunctionalRequirement list)

Output:
  Structured Markdown BRD (str), written to --out or stdout.

Rules:
  - No storytelling fluff
  - No hallucinated business logic
  - Language is professional and precise
  - Every section derives exclusively from the provided inputs
  - Risks are derived from missing data or low-confidence features (confidence < 0.6)
  - Assumptions are derived strictly from evidence gaps in the input
"""

from __future__ import annotations

import json
import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Any


# ---------------------------------------------------------------------------
# Section builders (each returns a Markdown string)
# ---------------------------------------------------------------------------

def _section_executive_summary(
    business_context: Dict,
    features: List[Dict]
) -> str:
    product_type = business_context.get("product_type", "Software System")
    core_value   = business_context.get("core_value", "Provides system-level functionality.")
    feat_count   = len(features)

    return (
        "## 1. Executive Summary\n\n"
        f"This document specifies the business requirements for a **{product_type}**. "
        f"The system encompasses {feat_count} identifiable functional capability(ies). "
        f"{core_value}\n\n"
        "_This document is generated deterministically from structured pipeline output. "
        "No business logic has been inferred beyond the provided evidence._\n"
    )


def _section_product_overview(
    business_context: Dict,
    features: List[Dict]
) -> str:
    product_type  = business_context.get("product_type", "Software System")
    core_value    = business_context.get("core_value", "")

    # Core capabilities: take feature names with confidence >= 0.6
    high_conf = [
        f.get("name", "").replace("_", " ").title()
        for f in features
        if float(f.get("confidence", 0)) >= 0.6
    ]

    capabilities_md = "\n".join(f"- {c}" for c in high_conf) if high_conf else "- No high-confidence capabilities detected."

    return (
        "## 2. Product Overview\n\n"
        f"| Field | Value |\n"
        f"|---|---|\n"
        f"| **System Type** | {product_type} |\n"
        f"| **Core Value Statement** | {core_value} |\n\n"
        "**Core Capabilities:**\n\n"
        f"{capabilities_md}\n"
    )


def _section_stakeholders(business_context: Dict) -> str:
    users = business_context.get("primary_users", [])
    if not users:
        users = ["General System Users"]

    rows = "\n".join(f"| {u} | Derived from feature evidence |" for u in users)
    return (
        "## 3. Stakeholders\n\n"
        "| User Type | Basis |\n"
        "|---|---|\n"
        f"{rows}\n"
    )


def _section_feature_breakdown(features: List[Dict]) -> str:
    if not features:
        return "## 4. Feature Breakdown\n\n_No features identified._\n"

    lines = ["## 4. Feature Breakdown\n"]
    for feat in features:
        name        = feat.get("name", "unnamed").replace("_", " ").title()
        description = feat.get("description", "No description provided.")
        evidence    = feat.get("evidence", [])
        confidence  = float(feat.get("confidence", 0))

        evidence_str = ", ".join(f"`{e}`" for e in evidence) if evidence else "_None_"
        conf_str     = f"{confidence:.0%}"

        lines.append(f"### {name}\n")
        lines.append(f"- **Description:** {description}")
        lines.append(f"- **Evidence:** {evidence_str}")
        lines.append(f"- **Confidence:** {conf_str}\n")

    return "\n".join(lines)


def _section_functional_requirements(frs: List[Dict]) -> str:
    if not frs:
        return "## 5. Functional Requirements\n\n_No functional requirements generated._\n"

    lines = ["## 5. Functional Requirements\n"]
    for fr in frs:
        fr_id       = fr.get("id", "FR-?")
        description = fr.get("description", "")
        linked      = fr.get("linked_feature", fr.get("mapped_feature", "unknown")).replace("_", " ").title()
        criteria    = fr.get("acceptance_criteria", [])

        lines.append(f"### {fr_id} — {linked}\n")
        lines.append(f"{description}\n")
        if criteria:
            lines.append("**Acceptance Criteria:**\n")
            for ac in criteria:
                lines.append(f"- {ac}")
            lines.append("")

    return "\n".join(lines)


def _section_non_functional_requirements(nfrs: List[Dict]) -> str:
    if not nfrs:
        return "## 6. Non-Functional Requirements\n\n_No non-functional requirements generated._\n"

    # Group by category
    categories: Dict[str, List[str]] = {}
    for nfr in nfrs:
        cat  = nfr.get("category", nfr.get("type", "uncategorized")).capitalize()
        desc = nfr.get("description", "")
        nfr_id = nfr.get("id", "NFR-?")
        categories.setdefault(cat, []).append(f"- **{nfr_id}:** {desc}")

    lines = ["## 6. Non-Functional Requirements\n"]
    for cat, items in sorted(categories.items()):
        lines.append(f"### {cat}\n")
        lines.extend(items)
        lines.append("")

    return "\n".join(lines)


def _section_assumptions(
    business_context: Dict,
    features: List[Dict],
    frs: List[Dict],
    nfrs: List[Dict]
) -> str:
    assumptions = []

    # Assumption 1: if primary_users could not be precisely derived
    users = business_context.get("primary_users", [])
    if "General System Users" in users:
        assumptions.append(
            "User roles and access levels have not been explicitly defined in the feature set. "
            "The system is assumed to serve general authenticated users unless further context is provided."
        )

    # Assumption 2: if feature confidence is mixed
    low_conf_count = sum(1 for f in features if float(f.get("confidence", 1)) < 0.6)
    if low_conf_count > 0:
        assumptions.append(
            f"{low_conf_count} feature(s) carried a confidence score below 60%, indicating the corresponding "
            "modules or source files may be incomplete, ambiguous, or partially implemented."
        )

    # Assumption 3: if no tech-specific NFRs were generated (generic baseline only)
    if len(nfrs) <= 3:
        assumptions.append(
            "Tech stack input was not provided or insufficient. "
            "Non-functional requirements are based on generic system baselines only."
        )

    if not assumptions:
        assumptions.append(
            "All inputs were well-defined. No significant evidence gaps were detected."
        )

    lines = ["## 7. Assumptions\n"]
    for a in assumptions:
        lines.append(f"- {a}")
    lines.append("")

    return "\n".join(lines)


def _section_risks(features: List[Dict]) -> str:
    risks = []

    for feat in features:
        name       = feat.get("name", "unnamed").replace("_", " ").title()
        confidence = float(feat.get("confidence", 1))
        evidence   = feat.get("evidence", [])

        if confidence < 0.4:
            risks.append(
                f"**{name}** — Confidence {confidence:.0%}: Critical uncertainty. "
                "This capability may not be fully implemented or its source module is absent. "
                "Requirements derived from this feature should be validated before commitment."
            )
        elif confidence < 0.6:
            risks.append(
                f"**{name}** — Confidence {confidence:.0%}: Moderate uncertainty. "
                "Evidence is thin. Acceptance criteria should be verified against the actual implementation."
            )
        elif not evidence:
            risks.append(
                f"**{name}**: No evidence references were provided. "
                "Functional requirements linked to this feature lack traceable source validation."
            )

    if not risks:
        risks.append(
            "No high-risk features identified. All features carry confidence scores ≥ 60% with evidence references."
        )

    lines = ["## 8. Risks\n"]
    for r in risks:
        lines.append(f"- {r}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compose_brd(
    business_context: Dict,
    features: List[Dict],
    functional_requirements: List[Dict],
    non_functional_requirements: List[Dict],
) -> str:
    """
    Compose a structured, enterprise-grade BRD in Markdown.

    All content is derived exclusively from the provided inputs.
    No LLM inference. No external assumptions.
    """
    today = date.today().strftime("%B %d, %Y")
    product_type = business_context.get("product_type", "Software System")

    sections = [
        f"# Business Requirement Document\n",
        f"**Document Type:** Business Requirement Document  ",
        f"**Generated Date:** {today}  ",
        f"**System:** {product_type}  ",
        f"**Status:** Draft  \n",
        "---\n",
        _section_executive_summary(business_context, features),
        "---\n",
        _section_product_overview(business_context, features),
        "---\n",
        _section_stakeholders(business_context),
        "---\n",
        _section_feature_breakdown(features),
        "---\n",
        _section_functional_requirements(functional_requirements),
        "---\n",
        _section_non_functional_requirements(non_functional_requirements),
        "---\n",
        _section_assumptions(business_context, features, functional_requirements, non_functional_requirements),
        "---\n",
        _section_risks(features),
    ]

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BRDComposer: Compose enterprise BRD from pipeline JSON outputs.")
    parser.add_argument("--business-context", required=True, help="Path to business_context JSON")
    parser.add_argument("--features",          required=True, help="Path to features JSON")
    parser.add_argument("--functional",        required=True, help="Path to functional_requirements JSON")
    parser.add_argument("--non-functional",    required=True, help="Path to non_functional_requirements JSON")
    parser.add_argument("--out",               default=None,  help="Output .md path (prints to stdout if omitted)")
    args = parser.parse_args()

    def _load(path_str: str) -> Any:
        p = Path(path_str)
        if not p.exists():
            print(f"[ERROR] File not found: {p}", file=sys.stderr)
            sys.exit(1)
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    # Load all inputs
    raw_biz  = _load(args.business_context)
    raw_feat = _load(args.features)
    raw_fr   = _load(args.functional)
    raw_nfr  = _load(args.non_functional)

    # Resolve nesting
    biz_ctx = raw_biz.get("business_context", raw_biz) if isinstance(raw_biz, dict) else {}
    feat_list = (
        raw_feat.get("features", raw_feat.get("validated_features", raw_feat))
        if isinstance(raw_feat, dict) else raw_feat
    ) or []
    fr_list = (
        raw_fr.get("functional_requirements", raw_fr)
        if isinstance(raw_fr, dict) else raw_fr
    ) or []
    nfr_list = (
        raw_nfr.get("non_functional_requirements", raw_nfr)
        if isinstance(raw_nfr, dict) else raw_nfr
    ) or []

    markdown = compose_brd(biz_ctx, feat_list, fr_list, nfr_list)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"[OK] BRD written to {out_path}", file=sys.stderr)
    else:
        print(markdown)
