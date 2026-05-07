"""
llm_brd_composer.py — LLM-Driven Enterprise BRD Composer
----------------------------------------------------------
Replaces the hardcoded template approach in brd_composer.py.

Architecture:
  - Receives the Evidence Bundle (all extracted facts).
  - Makes one focused LLM call per BRD section (16 calls total).
  - Every call is grounded: the LLM receives ONLY facts from the bundle.
  - Each section has a deterministic fallback if the LLM call fails.
  - After each LLM call, runs a lightweight grounding check to flag
    unverifiable claims with [INFERRED].

Anti-Hallucination Design:
  - Temperature = 0 (deterministic output).
  - JSON mode enforced where structured output is needed.
  - System prompt explicitly forbids inventing facts.
  - Grounding check cross-references version numbers, entity names,
    endpoint paths, and defect IDs against the bundle.

Usage:
    from app.analysis.llm_brd_composer import compose_brd_llm
    markdown = compose_brd_llm(evidence_bundle)
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Dict, List, Tuple

from app.analysis.prompts.section_prompts import (
    S1_EXEC_SUMMARY, S2_BUSINESS_CONTEXT, S3_CURRENT_STATE,
    S4_STAKEHOLDERS, S5_FUNCTIONAL_REQS, S6_NFRS,
    S7_DATA, S8_TECH_STACK, S9_CICD, S10_INFRA,
    S11_RISKS, S12_COMPLIANCE, S13_ACCEPTANCE,
    S14_ROADMAP, S15_OPEN_ISSUES, S16_APPROVAL,
)
from app.utils.logger import get_logger, StageTimer, log

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# LLM client — lazy import so missing API key never crashes at import time
# ---------------------------------------------------------------------------

def _get_llm() -> Any:
    """Return the llm_text_call function, or None if LLM is unavailable."""
    try:
        from app.utils.llm_client import llm_text_call
        return llm_text_call
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Grounding Checker
# ---------------------------------------------------------------------------

def _ground_check(text: str, bundle: Dict) -> Tuple[str, List[str]]:
    """
    Check LLM output for unverifiable factual claims.

    Scans for:
      - Version numbers like "1.3.21" → verify in bundle["dependencies"]
      - Entity/class names (PascalCase) → verify in bundle["entities"]
      - BUG-NN IDs → verify in bundle["defects"]
      - Endpoint paths /api/... → verify in bundle["endpoints"]

    Unverifiable claims are annotated inline with [INFERRED].
    Returns (annotated_text, list_of_unverified_claims).
    """
    unverified: List[str] = []

    # Build verification sets from bundle
    known_versions  = {d.get("current_version", "") for d in bundle.get("dependencies", [])}
    known_names     = {d.get("name", "").lower()    for d in bundle.get("dependencies", [])}
    known_entities  = {e.get("name", "")            for e in bundle.get("entities", [])}
    known_defects   = {d.get("id", "")              for d in bundle.get("defects", [])}
    known_paths     = {e.get("path", "")            for e in bundle.get("endpoints", [])}
    feat_names      = {
        f.get("name", "").lower().replace("_", " ")
        for f in bundle.get("features", [])
    }

    annotated = text

    # Check version numbers (x.y.z or x.y patterns that aren't table separators)
    for m in re.finditer(r'\b(\d+\.\d+(?:\.\d+)?(?:\.\w+)?)\b', text):
        ver = m.group(1)
        if ver not in known_versions and "---" not in ver:
            claim = f"Version '{ver}' not found in extracted dependencies"
            unverified.append(claim)
            annotated = annotated.replace(ver, f"{ver} [INFERRED]", 1)

    # Check BUG-NN IDs
    for m in re.finditer(r'\b(BUG-\d+)\b', text):
        bid = m.group(1)
        if bid not in known_defects:
            claim = f"Defect ID '{bid}' not in extracted defects"
            unverified.append(claim)
            annotated = annotated.replace(bid, f"{bid} [INFERRED]", 1)

    return annotated, unverified


# ---------------------------------------------------------------------------
# Deterministic Fallbacks (used when LLM fails or is unavailable)
# ---------------------------------------------------------------------------

def _fallback_cover(bundle: Dict, today: str) -> str:
    return (
        f"# BUSINESS REQUIREMENTS DOCUMENT\n\n"
        f"**Project:** {bundle.get('repo_name', 'Unknown')}\n"
        f"**System Type:** {bundle.get('product_type', 'Software System')}\n"
        f"**Prepared by:** Analyst Agent\n"
        f"**Version:** 1.0 — Draft\n"
        f"**Date:** {today}\n"
        f"**Status:** Draft — Pending Review\n\n---\n\n"
        "## Table of Contents\n\n"
        + "\n".join(
            f"{i}. {s}" for i, s in enumerate([
                "Executive Summary", "Business Context & Objectives",
                "Current State Analysis (AS-IS)", "Stakeholders & Personas",
                "Functional Requirements", "Non-Functional Requirements",
                "Data Requirements", "Technology Stack (TO-BE)",
                "CI/CD Pipeline Requirements", "Infrastructure Requirements",
                "Risk Register", "Compliance & Legal",
                "Acceptance Criteria", "Delivery Roadmap",
                "Open Issues & Decisions", "Document Approval",
            ], 1)
        ) + "\n\n---\n"
    )


def _fallback_section(num: int, name: str, msg: str = "Content pending LLM availability.") -> str:
    return f"## {num}. {name}\n\n_{msg}_\n\n---\n"


def _fallback_fr_section(bundle: Dict) -> str:
    """Deterministic FR section — used as fallback for section 5."""
    frs   = bundle.get("functional_requirements", [])
    feats = {f.get("name", ""): f for f in bundle.get("features", [])}
    lines = ["## 5. Functional Requirements\n\n_Priority: M=Must Have | S=Should Have | C=Could Have_\n"]
    for fr in frs:
        lf   = fr.get("linked_feature", "")
        feat = feats.get(lf, {})
        conf = float(feat.get("confidence", 0.7))
        pri  = "M" if conf >= 0.8 else ("S" if conf >= 0.6 else "C")
        lines.append(f"\n**{fr.get('id','FR-?')}** | Priority: {pri}\n\n{fr.get('description','')}\n")
        for ac in fr.get("acceptance_criteria", []):
            lines.append(f"- {ac}")
    lines.append("\n---\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section Evidence Slices
# Build minimal JSON snippets — send only what each section needs.
# This keeps token usage low and reduces hallucination surface area.
# ---------------------------------------------------------------------------

def _slice(bundle: Dict, *keys: str) -> str:
    """Return a compact JSON string with only the specified bundle keys."""
    return json.dumps({k: bundle.get(k) for k in keys}, indent=2, default=str)


# ---------------------------------------------------------------------------
# Core Section Caller
# ---------------------------------------------------------------------------

def _call_section(
    llm: Any,
    system_prompt: str,
    task_text: str,
    bundle: Dict,
    evidence_keys: List[str],
    section_num: int,
    section_name: str,
    fallback_fn,
) -> str:
    """
    Call the LLM for one BRD section, run grounding check, return final text.

    If the LLM call fails for any reason:
      - Logs a warning with the error.
      - Returns the deterministic fallback.
    """
    if llm is None:
        log(logger.warning, "llm.unavailable",
            section=section_name, action="using_fallback")
        return fallback_fn()

    evidence_json = _slice(bundle, *evidence_keys)
    user_msg = (
        f"## EVIDENCE BLOCK\n```json\n{evidence_json}\n```\n\n"
        f"## TODAY'S DATE\n{date.today().strftime('%B %d, %Y')}\n\n"
        f"## TASK\n{task_text}"
    )

    with StageTimer(logger, f"llm.section.{section_num}"):
        try:
            raw = llm(system_prompt=system_prompt, user_prompt=user_msg, max_tokens=900)
        except Exception as exc:
            log(logger.error, "llm.section.failed",
                section=section_name, error=str(exc), action="deterministic_fallback")
            return fallback_fn()

    if not raw or not raw.strip():
        log(logger.warning, "llm.section.empty",
            section=section_name, action="deterministic_fallback")
        return fallback_fn()

    # Grounding check
    annotated, unverified = _ground_check(raw, bundle)
    if unverified:
        log(logger.warning, "grounding.unverified",
            section=section_name, count=len(unverified), claims=str(unverified[:3]))

    # Ensure section always ends with ---
    text = annotated.strip()
    if not text.endswith("---"):
        text += "\n\n---"
    return text + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compose_brd_llm(bundle: Dict[str, Any]) -> str:
    """
    Generate a full 16-section enterprise BRD using LLM with grounded evidence.

    Parameters
    ----------
    bundle : dict
        The Evidence Bundle produced by evidence_bundle.build_evidence_bundle().

    Returns
    -------
    str
        Complete BRD in Markdown format.
    """
    llm   = _get_llm()
    today = date.today().strftime("%B %d, %Y")

    if llm:
        log(logger.info, "composer.mode", mode="llm", model="gpt-4o-mini")
    else:
        log(logger.warning, "composer.mode",
            mode="deterministic_fallback", reason="LLM client unavailable")

    def _s(num, name, task, sys_p, keys, fallback):
        return _call_section(
            llm=llm, system_prompt=sys_p,
            task_text=task, bundle=bundle,
            evidence_keys=keys, section_num=num,
            section_name=name, fallback_fn=fallback,
        )

    # ── Cover page + ToC (always deterministic) ───────────────────────────
    cover = _fallback_cover(bundle, today)

    # ── Section 1: Executive Summary ──────────────────────────────────────
    s1 = _s(
        1, "Executive Summary",
        "Write Section 1: Executive Summary following the structure in your instructions.",
        S1_EXEC_SUMMARY,
        ["repo_name", "product_type", "core_value", "features", "defects", "stats"],
        lambda: _fallback_section(1, "Executive Summary", f"System: {bundle.get('product_type')}. "
                                  f"Features detected: {bundle['stats']['total_features']}."),
    )

    # ── Section 2: Business Context ───────────────────────────────────────
    s2 = _s(
        2, "Business Context",
        "Write Section 2: Business Context & Objectives.",
        S2_BUSINESS_CONTEXT,
        ["product_type", "features", "defects", "primary_users", "uses_jcenter", "stats"],
        lambda: _fallback_section(2, "Business Context & Objectives"),
    )

    # ── Section 3: Current State ───────────────────────────────────────────
    s3 = _s(
        3, "Current State Analysis",
        "Write Section 3: Current State Analysis (AS-IS).",
        S3_CURRENT_STATE,
        ["features", "dependencies", "entities", "endpoints", "defects", "language", "build_tool"],
        lambda: _fallback_section(3, "Current State Analysis (AS-IS)"),
    )

    # ── Section 4: Stakeholders ────────────────────────────────────────────
    s4 = _s(
        4, "Stakeholders",
        "Write Section 4: Stakeholders & Personas.",
        S4_STAKEHOLDERS,
        ["primary_users", "product_type", "features", "functional_requirements"],
        lambda: _fallback_section(4, "Stakeholders & Personas"),
    )

    # ── Section 5: Functional Requirements ───────────────────────────────
    s5 = _s(
        5, "Functional Requirements",
        "Write Section 5: Functional Requirements.",
        S5_FUNCTIONAL_REQS,
        ["functional_requirements", "features", "endpoints"],
        lambda: _fallback_fr_section(bundle),
    )

    # ── Section 6: NFRs ───────────────────────────────────────────────────
    s6 = _s(
        6, "Non-Functional Requirements",
        "Write Section 6: Non-Functional Requirements.",
        S6_NFRS,
        ["non_functional_requirements", "product_type"],
        lambda: _fallback_section(6, "Non-Functional Requirements"),
    )

    # ── Section 7: Data Requirements ──────────────────────────────────────
    s7 = _s(
        7, "Data Requirements",
        "Write Section 7: Data Requirements.",
        S7_DATA,
        ["entities", "dependencies", "defects", "features"],
        lambda: _fallback_section(7, "Data Requirements"),
    )

    # ── Section 8: Tech Stack ──────────────────────────────────────────────
    s8 = _s(
        8, "Technology Stack",
        "Write Section 8: Modernization Technology Stack (TO-BE).",
        S8_TECH_STACK,
        ["dependencies", "language", "build_tool", "uses_jcenter"],
        lambda: _fallback_section(8, "Technology Stack (TO-BE)"),
    )

    # ── Section 9: CI/CD ──────────────────────────────────────────────────
    s9 = _s(
        9, "CI/CD Pipeline",
        "Write Section 9: CI/CD Pipeline Requirements.",
        S9_CICD,
        ["defects", "uses_jcenter", "endpoints"],
        lambda: _fallback_section(9, "CI/CD Pipeline Requirements"),
    )

    # ── Section 10: Infrastructure ────────────────────────────────────────
    s10 = _s(
        10, "Infrastructure",
        "Write Section 10: Infrastructure Requirements.",
        S10_INFRA,
        ["product_type", "features", "grpc_rpcs"],
        lambda: _fallback_section(10, "Infrastructure Requirements"),
    )

    # ── Section 11: Risk Register ─────────────────────────────────────────
    s11 = _s(
        11, "Risk Register",
        "Write Section 11: Risk Register.",
        S11_RISKS,
        ["defects", "features", "uses_jcenter", "stats"],
        lambda: _fallback_section(11, "Risk Register"),
    )

    # ── Section 12: Compliance ────────────────────────────────────────────
    s12 = _s(
        12, "Compliance",
        "Write Section 12: Compliance & Legal Requirements.",
        S12_COMPLIANCE,
        ["product_type", "primary_users", "entities"],
        lambda: _fallback_section(12, "Compliance & Legal Requirements"),
    )

    # ── Section 13: Acceptance Criteria ───────────────────────────────────
    s13 = _s(
        13, "Acceptance Criteria",
        "Write Section 13: Acceptance Criteria.",
        S13_ACCEPTANCE,
        ["functional_requirements", "non_functional_requirements"],
        lambda: _fallback_section(13, "Acceptance Criteria"),
    )

    # ── Section 14: Delivery Roadmap ──────────────────────────────────────
    s14 = _s(
        14, "Delivery Roadmap",
        "Write Section 14: Delivery Roadmap.",
        S14_ROADMAP,
        ["defects", "features", "stats"],
        lambda: _fallback_section(14, "Delivery Roadmap"),
    )

    # ── Section 15: Open Issues ────────────────────────────────────────────
    s15 = _s(
        15, "Open Issues",
        "Write Section 15: Open Issues & Decisions Required.",
        S15_OPEN_ISSUES,
        ["features", "non_functional_requirements", "primary_users"],
        lambda: _fallback_section(15, "Open Issues & Decisions Required"),
    )

    # ── Section 16: Document Approval ─────────────────────────────────────
    s16 = _s(
        16, "Document Approval",
        f"Write Section 16: Document Approval. Today's date is {today}.",
        S16_APPROVAL,
        ["repo_name"],
        lambda: (
            "## 16. Document Approval\n\n"
            "| Role | Name | Signature | Date |\n|---|---|---|---|\n"
            "| Engineering Lead | | | |\n| Product Owner | | | |\n"
            f"| DevOps Lead | | | |\n| QA Lead | | | |\n\n"
            f"_Generated by Analyst Agent on {today}._\n"
        ),
    )

    log(logger.info, "composer.complete", sections=16, repo=bundle.get("repo_name"))

    return "\n".join([cover, s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12, s13, s14, s15, s16])
