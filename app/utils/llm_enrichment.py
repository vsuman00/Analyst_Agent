"""
llm_enrichment.py — Layer 3 Tool
----------------------------------
LLM Enrichment Layer

Sits between the deterministic pipeline stages and the BRD Composer.
Uses OpenAI to improve specific outputs that benefit from language generation:

  0. Feature Pruning        — Semantically validate extracted features to prune false positives.
  1. Feature Descriptions   — Enrich terse extracted feature descriptions with
                              one precise, professional sentence (grounded in evidence).
  2. Executive Summary      — Generate a concise (≤120 words) executive summary
                              grounded strictly in the input business context.
  3. Business Core Value    — Refine the core_value field in BusinessContext with
                              a professionally written value statement.
  4. Enterprise Artifacts   — Generate tailored Stakeholders, CI/CD, Infra, Data,
                              and Compliance standards.

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
# 0. Feature Pruning (Semantic Validation)
# ---------------------------------------------------------------------------

PRUNE_SYSTEM_PROMPT = """\
You are a Principal Software Architect reviewing an automated static analysis report.
You will be given a list of 'Extracted Features', the product README (if available), and a brief summary
of the repository's core modules.

Your job is to identify and REMOVE any features that are "false positives" (hallucinations)
caused by generic programming keywords being misinterpreted as business features.

For example:
- A Weather App might use the word "connection" for HTTP. If the report claims "Social Graph (Follow/Friend)"
  because of the word "connection", that is a false positive.
- A Resume Checker app should NOT have features like "PostgreSQL Database" or "AWS S3 Storage" unless
  the README or code explicitly mentions them.

STRICT RULES:
- Return ONLY a JSON object containing a list of the IDs of the VALID features.
- Schema: {"valid_feature_ids": ["feat-001", "feat-003"]}
- If all are valid, return all IDs.
- If none are valid, return an empty list: {"valid_feature_ids": []}
- Use the README as the PRIMARY source of truth for what features are real.
"""

def prune_hallucinated_features(
    features: List[Dict[str, Any]],
    repo_context,  # str (legacy) or dict (RepoContext from RepoContextBuilder)
) -> List[Dict[str, Any]]:
    """
    Uses the LLM to semantically validate extracted features and prune false positives.

    repo_context can be:
      - str  : legacy comma-separated module names (old pipeline path)
      - dict : RepoContext from RepoContextBuilder (new pipeline path, richer context)
    """
    if not features:
        return []

    feats_str = "\n".join([
        f"- {f.get('id')}: {f.get('name')} (Evidence: {', '.join(f.get('source_modules', []))})"
        for f in features
    ])

    # Build context string based on input type
    if isinstance(repo_context, dict):
        signals = repo_context.get("intent_signals", {})
        readme  = signals.get("readme", "")[:2000].strip()
        pkg_desc = signals.get("package_description", "")
        top_ctx  = f"README:\n{readme}\n\nPackage Description: {pkg_desc}" if readme else f"Package Description: {pkg_desc}"
    else:
        # Legacy: repo_context is a plain string of module names
        top_ctx = f"Repository Context / Top Modules: {repo_context}"

    user_prompt = (
        f"{top_ctx}\n\n"
        f"Extracted Features to Validate:\n{feats_str}\n\n"
        "Analyze these features against the README and return the JSON list of 'valid_feature_ids' "
        "that genuinely belong to this specific application."
    )

    try:
        result = llm_json_call(PRUNE_SYSTEM_PROMPT, user_prompt, max_tokens=500)
        if "valid_feature_ids" in result:
            valid_ids = result["valid_feature_ids"]
            return [f for f in features if f.get("id") in valid_ids]
        return features
    except Exception as e:
        print(f"[LLM ENRICHMENT] Feature pruning failed, returning original features. Error: {e}")
        return features


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

# ---------------------------------------------------------------------------
# 4. Enterprise Artifacts Generation (NEW)
# ---------------------------------------------------------------------------

ENTERPRISE_ARTIFACTS_PROMPT = """\
You are an enterprise technical architect. Given a software system's context and a codebase Evidence Checklist, \
generate specific, tailored enterprise artifacts. Do NOT use generic placeholders. \
Tailor the infrastructure, data, compliance, and CI/CD standards to the actual tech stack and features provided.

STRICT RULES:
1. Do NOT assume or generate Kubernetes or Docker-related infrastructure or CI/CD pipelines unless they are marked as 'SUPPORTED' in the provided Evidence Checklist.
2. Do NOT mention specific compliance standards like GDPR, CCPA, or HIPAA unless marked as 'SUPPORTED' in the provided Evidence Checklist.
3. Do NOT mention specific platform clients like iOS, Android, or Google Play/App Store unless marked as 'SUPPORTED' in the provided Evidence Checklist.
4. If a technology or standard is NOT supported in the Evidence Checklist, provide a generic, lightweight, and grounded alternative appropriate for the tech stack (e.g., standard Python logging instead of ELK cluster, local process execution or systemd instead of Docker/Kubernetes, basic data security/credential hashing instead of GDPR compliance, standard REST API standards instead of gRPC, etc.).

Return ONLY valid JSON matching this schema:
{
  "stakeholders": [{"role": "string", "responsibility": "string", "impact": "High|Medium|Low"}],
  "data_requirements": [{"requirement": "string", "specification": "string"}],
  "infrastructure": [{"aspect": "string", "specification": "string"}],
  "cicd_standards": [{"id": "CI-01", "standard": "string"}],
  "compliance": [{"domain": "string", "requirement": "string", "strategy": "string"}],
  "risks": [{"id": "R-01", "description": "string", "probability": "High|Medium|Low", "impact": "High|Medium|Low", "mitigation": "string"}]
}
"""

def enrich_enterprise_artifacts(
    business_context: Dict,
    features: List[Dict],
    tech_stack: List[str],
    evidence: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Use LLM to generate domain-specific content for the enterprise BRD sections (Data, CI/CD, Infra, etc.).
    Returns an empty dict if it fails, which the composer will handle via fallbacks.
    """
    feature_names = [f.get("name", "").replace("_", " ") for f in features[:10]]
    evidence = evidence or {}

    evidence_checklist = [
        f"- Docker containerization: {'SUPPORTED (Dockerfile/compose found)' if evidence.get('has_docker') else 'NOT SUPPORTED (No Docker files)'}",
        f"- Kubernetes orchestration: {'SUPPORTED (k8s/helm manifests found)' if evidence.get('has_kubernetes') else 'NOT SUPPORTED (No k8s files)'}",
        f"- HTTP REST API: {'SUPPORTED (HTTP endpoints found)' if evidence.get('has_http_api') else 'NOT SUPPORTED'}",
        f"- gRPC services: {'SUPPORTED (proto files/rpcs found)' if evidence.get('has_grpc') else 'NOT SUPPORTED'}",
        f"- Database: {'SUPPORTED (database dependencies found)' if evidence.get('has_database') else 'NOT SUPPORTED'}",
        f"- Authentication: {'SUPPORTED (auth dependencies/dirs found)' if evidence.get('has_auth') else 'NOT SUPPORTED'}",
        f"- Android mobile client: {'SUPPORTED (AndroidManifest found)' if evidence.get('has_android') else 'NOT SUPPORTED'}",
        f"- iOS mobile client: {'SUPPORTED (Xcode/Podfile found)' if evidence.get('has_ios') else 'NOT SUPPORTED'}",
        f"- GDPR/Compliance: {'SUPPORTED (Explicit GDPR/PII mention in docs)' if evidence.get('has_gdpr_mention') else 'NOT SUPPORTED (No GDPR/PII mention)'}",
    ]
    
    user_prompt = (
        f"System Type: {business_context.get('product_type', 'Software System')}\n"
        f"Tech Stack: {', '.join(tech_stack) if tech_stack else 'Unknown/Generic'}\n"
        f"Core Features: {', '.join(feature_names)}\n"
        f"Evidence Checklist (From codebase analysis):\n"
        f"{chr(10).join(evidence_checklist)}\n\n"
        "Generate the enterprise artifacts JSON."
    )
    
    try:
        # High max_tokens because it generates a lot of JSON
        result = llm_json_call(ENTERPRISE_ARTIFACTS_PROMPT, user_prompt, max_tokens=1500)
        return result
    except Exception as e:
        print(f"[LLM ENRICHMENT] Enterprise artifacts generation failed. Error: {e}")
        return {}
