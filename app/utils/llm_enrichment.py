"""
llm_enrichment.py — Layer 3 Tool
----------------------------------
LLM Enrichment Layer

Sits between the deterministic pipeline stages and the BRD Composer.
Uses OpenAI to improve three specific outputs that benefit from language generation:

  1. Feature Descriptions   — Enrich terse extracted feature descriptions with
                              one precise, professional sentence (grounded in evidence).
  2. Executive Summary      — Generate a concise (≤120 words) executive summary
                              grounded strictly in the input business context.
  3. Business Core Value    — Refine the core_value field in BusinessContext with
                              a professionally written value statement.

Rules (enforced in prompts and post-processing):
  - LLM MUST NOT invent features, requirements, or stakeholders.
  - All prompts supply the full structured context so the model has no reason to guess.
  - Outputs are validated: if the LLM returns empty or malformed content,
    the original deterministic value is preserved (safe fallback).
  - temperature = 0 (via llm_client) — deterministic output.

Usage:
    from app.utils.llm_enrichment import enrich_features, enrich_executive_summary

    enriched_features = enrich_features(features)
    summary = enrich_executive_summary(business_context, features)
"""

from __future__ import annotations

import json
from typing import Dict, List, Any

from app.utils.llm_client import llm_json_call, llm_text_call


# ---------------------------------------------------------------------------
# 1. Feature Description Enrichment
# ---------------------------------------------------------------------------

FEATURE_SYSTEM_PROMPT = """\
You are a senior technical analyst. You will be given a software feature extracted \
from a codebase. Your task is to rewrite the description as one precise, professional \
sentence that clearly states what the feature does, using SHALL language. 

STRICT RULES:
- Do NOT invent capabilities not present in the evidence list.
- Do NOT use marketing language (avoid: seamlessly, robust, world-class, etc.).
- Return ONLY valid JSON: {"description": "<your one sentence here>"}
"""

def enrich_features(features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enrich each feature's description using an LLM call.
    Falls back to the original description if the LLM call fails or returns empty.

    Returns an updated copy of the features list.
    """
    enriched = []
    for feat in features:
        original_desc = feat.get("description", "")
        evidence_str  = ", ".join(feat.get("evidence", feat.get("source_modules", [])))
        name          = feat.get("name", "unknown")

        user_prompt = (
            f"Feature name: {name}\n"
            f"Current description: {original_desc}\n"
            f"Supporting evidence: {evidence_str}\n\n"
            "Rewrite the description as one precise, professional SHALL-style sentence."
        )

        try:
            result    = llm_json_call(FEATURE_SYSTEM_PROMPT, user_prompt, max_tokens=120)
            new_desc  = result.get("description", "").strip()
            feat_copy = dict(feat)
            feat_copy["description"] = new_desc if new_desc else original_desc
        except Exception as e:
            print(f"[LLM ENRICHMENT] Feature '{name}' enrichment failed, using original. Error: {e}")
            feat_copy = dict(feat)  # preserve original

        enriched.append(feat_copy)
    return enriched


# ---------------------------------------------------------------------------
# 2. Executive Summary Generation
# ---------------------------------------------------------------------------

EXEC_SUMMARY_SYSTEM_PROMPT = """\
You are a senior enterprise technical writer. Given structured information about a \
software system, generate a concise executive summary of ≤120 words. 

STRICT RULES:
- Derive content ONLY from the provided JSON input.
- Do NOT invent users, markets, or business outcomes not present in the data.
- Use formal, professional language. No marketing fluff.
- Return ONLY valid JSON: {"executive_summary": "<your summary here>"}
"""

def enrich_executive_summary(
    business_context: Dict[str, Any],
    features: List[Dict[str, Any]],
) -> str:
    """
    Generate an LLM-written executive summary grounded in the pipeline outputs.
    Falls back to a template string if the LLM call fails.
    """
    feature_names = [f.get("name", "").replace("_", " ") for f in features[:8]]

    user_prompt = (
        f"System type: {business_context.get('product_type', 'Software System')}\n"
        f"Primary users: {', '.join(business_context.get('primary_users', ['end users']))}\n"
        f"Core value: {business_context.get('core_value', '')}\n"
        f"Top features: {', '.join(feature_names)}\n\n"
        "Write a concise executive summary (≤120 words) for this system."
    )

    try:
        result  = llm_json_call(EXEC_SUMMARY_SYSTEM_PROMPT, user_prompt, max_tokens=200)
        summary = result.get("executive_summary", "").strip()
        return summary if summary else _fallback_summary(business_context, features)
    except Exception as e:
        print(f"[LLM ENRICHMENT] Executive summary generation failed, using fallback. Error: {e}")
        return _fallback_summary(business_context, features)


def _fallback_summary(business_context: Dict, features: List[Dict]) -> str:
    product_type = business_context.get("product_type", "Software System")
    core_value   = business_context.get("core_value", "Provides system-level functionality.")
    return (
        f"This document specifies the business requirements for a {product_type}. "
        f"The system encompasses {len(features)} identifiable functional capability(ies). "
        f"{core_value}"
    )


# ---------------------------------------------------------------------------
# 3. Business Core Value Refinement
# ---------------------------------------------------------------------------

CORE_VALUE_SYSTEM_PROMPT = """\
You are a senior product strategist. Given a list of software features, write a single \
concise sentence (≤30 words) describing the core value the system delivers to its users.

STRICT RULES:
- Derive from the feature list ONLY. No external assumptions.
- No marketing language. No vague claims.
- Return ONLY valid JSON: {"core_value": "<your sentence here>"}
"""

def enrich_core_value(features: List[Dict[str, Any]]) -> str:
    """
    Use LLM to generate a precise core value statement from the features list.
    Falls back to the deterministic template if the call fails.
    """
    top_features = [f.get("name", "").replace("_", " ") for f in features[:5]]

    user_prompt = (
        f"Features implemented by this system: {', '.join(top_features)}\n\n"
        "In one sentence (≤30 words), state the core value this system delivers."
    )

    try:
        result     = llm_json_call(CORE_VALUE_SYSTEM_PROMPT, user_prompt, max_tokens=80)
        core_value = result.get("core_value", "").strip()
        return core_value if core_value else _fallback_core_value(features)
    except Exception as e:
        print(f"[LLM ENRICHMENT] Core value enrichment failed, using fallback. Error: {e}")
        return _fallback_core_value(features)


def _fallback_core_value(features: List[Dict]) -> str:
    top = [f.get("name", "").replace("_", " ").title() for f in features[:3]]
    if not top:
        return "Delivers core system functionality."
    return "Delivers " + ", ".join(top) + " functionality."
