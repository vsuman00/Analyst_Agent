"""
brd_enrichment_agent.py — BRD Deep Enrichment Agent
------------------------------------------------------
Enriches business_context with deeply detailed, grounded LLM content for each
BRD section. Strictly no hallucination — every claim traces to extracted data.

GROUNDING CONTRACT (every prompt):
  - Full structured JSON context injected (not just names).
  - Explicit instruction: derive ONLY from provided data.
  - If evidence insufficient → "Requires manual review."
  - temperature = 0 → deterministic output.

DUAL-LAYER WRITING (every prompt):
  - Business layer: plain English for non-technical stakeholders.
  - Technical layer: precise details in sub-sections only.
  - Acronyms explained on first use.
  - Glossary terms collected from every call → Section 17 of BRD.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Any

try:
    from app.utils.llm_client import llm_json_call
except ImportError:
    llm_json_call = None  # type: ignore


# ─── Shared Prompt Headers ────────────────────────────────────────────────────

_GROUNDING = """
GROUNDING RULES — MUST FOLLOW:
1. You are EXPLAINING provided data, not inventing. Every claim must trace to the JSON input.
2. If evidence is insufficient, write: "Requires manual review — insufficient data detected."
3. Do NOT invent: user counts, revenue figures, company names, SLA numbers, or technologies not in the JSON.
4. Do NOT use: "industry standard", "best practice", "cutting-edge" unless present in the input.
"""

_AUDIENCE = """
DUAL-AUDIENCE WRITING RULES — MUST FOLLOW:
1. Write for TWO audiences:
   - PRIMARY: Business stakeholder (non-technical). Must understand the "what" and "why".
   - SECONDARY: Engineering lead. Technical specifics go in "Technical Note:" sub-sections ONLY.
2. Plain English first. No raw jargon without explanation.
3. Explain acronyms on first use: "REST API (a standard web communication interface)" not just "REST API".
4. Forbidden in business-facing text (use plain alternatives):
   microservice, orchestration, idempotent, polymorphic, asynchronous, middleware.
5. Collect all technical terms you use into the glossary_terms output field.
"""


# ─── Helper ───────────────────────────────────────────────────────────────────

def _feat_context(features: List[Dict]) -> List[Dict]:
    return [
        {
            "name": f.get("name", "").replace("_", " "),
            "description": f.get("description", ""),
            "confidence": round(float(f.get("confidence", 0)), 2),
            "evidence": f.get("source_modules", f.get("merge_of", [])),
        }
        for f in features
    ]


def _safe_call(system: str, user: str, max_tokens: int, tag: str) -> Dict:
    try:
        result = llm_json_call(system, user, max_tokens=max_tokens)
        return result or {}
    except Exception as e:
        print(f"[BRD ENRICHMENT] {tag} failed: {e}")
        return {}


# ─── 1. Executive Summary ─────────────────────────────────────────────────────

_EXEC_SYS = f"""You are a senior enterprise technical writer producing the Executive Summary of a BRD.
{_GROUNDING}
{_AUDIENCE}

Write 3 paragraphs (150–200 words total):
  Para 1: What this system IS and what BUSINESS PROBLEM it solves. Start with the system name.
  Para 2: KEY capabilities found — summarise top features in business terms, not technical.
  Para 3: Why this BRD exists — what decisions it supports (budget, build, approval).

Return ONLY valid JSON:
{{
  "executive_summary": "<3-paragraph text>",
  "glossary_terms": [{{"term": "<word>", "plain_definition": "<one plain sentence>"}}]
}}"""


def enrich_executive_summary(biz_ctx: Dict, features: List[Dict], frs: List[Dict]) -> Dict:
    ctx = {
        "repo_name":         biz_ctx.get("repo_name", "Unknown System"),
        "product_type":      biz_ctx.get("product_type", "Software System"),
        "primary_users":     biz_ctx.get("primary_users", []),
        "core_value":        biz_ctx.get("core_value", ""),
        "product_summary":   biz_ctx.get("product_summary", ""),
        "core_capabilities": biz_ctx.get("core_capabilities", []),
        "tech_stack":        biz_ctx.get("tech_stack", []),
        "features":          _feat_context(features),
        "total_frs":         len(frs),
        # README injected as the primary product intent signal
        "readme_excerpt":    biz_ctx.get("readme_excerpt", ""),
    }
    return _safe_call(
        _EXEC_SYS,
        f"System data:\n```json\n{json.dumps(ctx, indent=2)}\n```\nWrite the Executive Summary.",
        600, "ExecutiveSummary"
    )


# ─── 2. Business Context ──────────────────────────────────────────────────────

_BIZ_SYS = f"""You are a senior business analyst writing the Business Context section of a BRD.
{_GROUNDING}
{_AUDIENCE}

Generate:
1. "problem_statement" (2–3 sentences): What business pain does this system address?
   Ground it in the features: e.g. auth features → "uncontrolled access risk".
2. "goals" (4 items): Specific, measurable goals derived from the feature set.
   Each goal needs a concrete metric. E.g.: "Reduce manual errors to zero by automating X."
3. "in_scope" (max 8 items): Features being delivered.
4. "out_of_scope" (3–4 items): What is explicitly excluded.

Return ONLY valid JSON:
{{
  "problem_statement": "<2-3 sentences>",
  "goals": [{{"id": "G-01", "goal": "<title>", "success_metric": "<measurable>", "linked_feature": "<name>"}}],
  "in_scope": ["<item>"],
  "out_of_scope": ["<item>"],
  "glossary_terms": [{{"term": "<word>", "plain_definition": "<definition>"}}]
}}"""


def enrich_business_context(biz_ctx: Dict, features: List[Dict]) -> Dict:
    ctx = {
        "repo_name":      biz_ctx.get("repo_name", "Unknown System"),
        "product_type":   biz_ctx.get("product_type", "Software System"),
        "tech_stack":     biz_ctx.get("tech_stack", []),
        "features":       _feat_context(features),
        # README injected so problem statement is grounded in real product pain
        "readme_excerpt": biz_ctx.get("readme_excerpt", ""),
    }
    return _safe_call(
        _BIZ_SYS,
        f"System data:\n```json\n{json.dumps(ctx, indent=2)}\n```\nGenerate the Business Context.",
        800, "BusinessContext"
    )


# ─── 3. Stakeholders ──────────────────────────────────────────────────────────

_STAKE_SYS = f"""You are a senior business analyst writing the Stakeholders section of a BRD.
{_GROUNDING}
{_AUDIENCE}

Infer SPECIFIC stakeholders from the detected features. Do NOT use generic "End User" or "Admin".
- payment/billing features → "Finance Manager", "Billing Analyst"
- auth/identity features → "Security Officer", "IT Administrator"
- reporting/analytics → "Operations Manager", "Data Analyst"
- API/integration → "Integration Partner", "Third-party Developer"

For each persona write: goal, pain point, technical literacy (Low/Medium/High), and needs.

Return ONLY valid JSON:
{{
  "stakeholders": [{{"role": "<specific role>", "responsibility": "<what they own>", "impact": "High|Medium|Low"}}],
  "personas": [{{
    "name": "<role>",
    "goal": "<what they want to achieve>",
    "pain_point": "<current frustration this system solves>",
    "technical_literacy": "Low|Medium|High",
    "needs": "<what the system must do for them>"
  }}],
  "glossary_terms": [{{"term": "<word>", "plain_definition": "<definition>"}}]
}}"""


def enrich_stakeholders(biz_ctx: Dict, features: List[Dict], tech_stack: List[str]) -> Dict:
    ctx = {
        "product_type": biz_ctx.get("product_type", "Software System"),
        "primary_users": biz_ctx.get("primary_users", []),
        "tech_stack": tech_stack,
        "features": _feat_context(features),
    }
    return _safe_call(
        _STAKE_SYS,
        f"System data:\n```json\n{json.dumps(ctx, indent=2)}\n```\nIdentify specific stakeholders and personas.",
        800, "Stakeholders"
    )


# ─── 4. Functional Requirements ───────────────────────────────────────────────

_FR_SYS = f"""You are a senior business analyst enriching Functional Requirements for a BRD.
{_GROUNDING}
{_AUDIENCE}

For each FR provided, generate:
1. "plain_english": What does this mean in business terms? (non-technical, 1 sentence)
   Example: "Users must be able to log in securely before accessing any information."
2. "technical_note": Precise technical specification for engineers (SHALL language).
   Example: "The system SHALL validate credentials and issue a signed JWT (a secure digital key)."
3. "business_impact": One sentence — what happens if this FR is NOT implemented?

Return ONLY valid JSON:
{{
  "enriched_frs": [{{
    "id": "<FR-N>",
    "plain_english": "<business-friendly>",
    "technical_note": "<SHALL-style technical>",
    "business_impact": "<consequence if missing>",
    "acceptance_criteria": ["<testable criterion>"]
  }}],
  "glossary_terms": [{{"term": "<word>", "plain_definition": "<definition>"}}]
}}"""


def enrich_functional_requirements(
    frs: List[Dict],
    features: List[Dict],
    batch_size: int = 8,
) -> Dict:
    """
    Enrich functional requirements in batches of `batch_size` (default 8) to prevent
    token-limit failures (finish_reason=length) on large repositories.

    All batches are merged into a single result dict:
      {"enriched_frs": [...], "glossary_terms": [...]}
    """
    if not frs:
        return {}

    feat_map = {
        f.get("name", ""): {
            "description": f.get("description", ""),
            "evidence": f.get("source_modules", f.get("merge_of", [])),
        }
        for f in features
    }
    frs_ctx = [
        {
            "id": fr.get("id", ""),
            "linked_feature": fr.get("linked_feature", "").replace("_", " "),
            "current_description": fr.get("description", ""),
            "feature_description": feat_map.get(fr.get("linked_feature", ""), {}).get("description", ""),
            "source_evidence": feat_map.get(fr.get("linked_feature", ""), {}).get("evidence", []),
            "acceptance_criteria": fr.get("acceptance_criteria", []),
        }
        for fr in frs
    ]

    # ── Batch processing ──────────────────────────────────────────────────────
    all_enriched: List[Dict] = []
    all_glossary: List[Dict] = []

    for batch_start in range(0, len(frs_ctx), batch_size):
        batch = frs_ctx[batch_start: batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        total_batches = (len(frs_ctx) + batch_size - 1) // batch_size
        print(f"[BRD ENRICHMENT] FR batch {batch_num}/{total_batches} ({len(batch)} FRs)...")

        result = _safe_call(
            _FR_SYS,
            f"FRs to enrich:\\n```json\\n{json.dumps(batch, indent=2)}\\n```\\nEnrich each requirement.",
            1500,
            f"FunctionalRequirements-batch{batch_num}",
        )
        all_enriched.extend(result.get("enriched_frs", []))
        all_glossary.extend(result.get("glossary_terms", []))

    return {"enriched_frs": all_enriched, "glossary_terms": all_glossary}



# ─── 5. NFR SLA Enrichment ────────────────────────────────────────────────────

_NFR_SYS = f"""You are a senior enterprise architect enriching Non-Functional Requirements for a BRD.
{_GROUNDING}
{_AUDIENCE}

For each NFR, provide:
1. "plain_english": What does this mean for the business? (non-technical)
2. "specific_target": A precise, measurable SLA derived from the system type.
   Auth service → "99.99% uptime — max 52 minutes downtime/year"
   Data platform → "Query response < 3 seconds for datasets up to 10M records"
   DO NOT use "Strict" as a target. Every target must be a concrete value.
3. "business_consequence": What happens if this SLA is missed?

Return ONLY valid JSON:
{{
  "enriched_nfrs": [{{
    "id": "<NFR-N>",
    "category": "<category>",
    "plain_english": "<non-technical explanation>",
    "specific_target": "<precise measurable SLA>",
    "business_consequence": "<impact if missed>"
  }}],
  "glossary_terms": [{{"term": "<word>", "plain_definition": "<definition>"}}]
}}"""


def enrich_nfrs(nfrs: List[Dict], system_type: str, tech_stack: List[str]) -> Dict:
    if not nfrs:
        return {}
    ctx = {
        "system_type": system_type,
        "tech_stack": tech_stack,
        "nfrs": [{"id": n.get("id"), "category": n.get("category"), "description": n.get("description")} for n in nfrs],
    }
    return _safe_call(
        _NFR_SYS,
        f"System data:\n```json\n{json.dumps(ctx, indent=2)}\n```\nEnrich each NFR with plain English and specific SLA.",
        1000, "NFRs"
    )


# ─── 6. Delivery Roadmap ──────────────────────────────────────────────────────

_ROADMAP_SYS = f"""You are a senior delivery manager writing the project roadmap for a BRD.
{_GROUNDING}
{_AUDIENCE}

Create a 4-phase roadmap mapping the actual detected features to delivery phases.
- High-confidence features (≥ 0.8) go in Phase 1–2. Low-confidence (< 0.6) go in Phase 3–4.
- Each phase must have a BUSINESS milestone name (e.g. "Core System Live", not "Phase 1").
- Definition of done must be in business terms, not technical terms.

Return ONLY valid JSON:
{{
  "phases": [{{
    "number": 1,
    "name": "<business milestone>",
    "focus": "<business capability unlocked>",
    "features_delivered": ["<feature name>"],
    "definition_of_done": "<plain English completion criteria>",
    "estimated_duration": "<N weeks>",
    "key_risks": ["<specific risk>"]
  }}],
  "glossary_terms": [{{"term": "<word>", "plain_definition": "<definition>"}}]
}}"""


def enrich_roadmap(features: List[Dict], frs: List[Dict]) -> Dict:
    if not features:
        return {}
    sorted_feats = sorted(features, key=lambda f: -float(f.get("confidence", 0)))
    ctx = {
        "total_features": len(features),
        "total_requirements": len(frs),
        "features": _feat_context(sorted_feats),
    }
    return _safe_call(
        _ROADMAP_SYS,
        f"Features:\n```json\n{json.dumps(ctx, indent=2)}\n```\nCreate 4-phase delivery roadmap.",
        1000, "Roadmap"
    )


# ─── 7. Open Issues ───────────────────────────────────────────────────────────

_ISSUES_SYS = f"""You are a senior business analyst identifying open issues for a BRD.
{_GROUNDING}
{_AUDIENCE}

Analyse the provided features and identify specific open questions. Focus on:
- Low-confidence features (< 0.6) needing discovery work
- Missing data (no tech stack, missing auth, no error handling evidence)
- Business decisions that cannot be made from code alone

Each issue must be a specific, actionable question — not vague.
Include who must answer it and the business impact of NOT resolving it.

Return ONLY valid JSON:
{{
  "issues": [{{
    "id": "OI-01",
    "question": "<specific open question>",
    "owner": "Business|Engineering|Both",
    "business_impact": "<consequence of leaving unresolved>",
    "recommended_action": "<concrete next step>",
    "priority": "High|Medium|Low"
  }}],
  "glossary_terms": [{{"term": "<word>", "plain_definition": "<definition>"}}]
}}"""


def enrich_open_issues(features: List[Dict], biz_ctx: Dict) -> Dict:
    low_conf = [f for f in features if float(f.get("confidence", 1)) < 0.6]
    ctx = {
        "product_type": biz_ctx.get("product_type", "Software System"),
        "tech_stack_detected": biz_ctx.get("tech_stack", []),
        "total_features": len(features),
        "low_confidence_features": _feat_context(low_conf),
        "signals": {
            "no_tech_stack": len(biz_ctx.get("tech_stack", [])) == 0,
            "has_auth": any("auth" in f.get("name", "") for f in features),
            "has_tests": any("test" in f.get("name", "") for f in features),
        },
    }
    return _safe_call(
        _ISSUES_SYS,
        f"Analysis:\n```json\n{json.dumps(ctx, indent=2)}\n```\nIdentify open issues and decisions.",
        800, "OpenIssues"
    )


# ─── Master Orchestrator ──────────────────────────────────────────────────────

def enrich_brd_context(
    biz_ctx: Dict,
    features: List[Dict],
    fr_dict: Dict,
    nfr_dict: Dict,
    repo_context: Dict = None,
) -> Dict:
    """
    Run all 7 enrichment functions and inject results into biz_ctx.
    Each enrichment is independently fallback-safe — failures never break the pipeline.

    If repo_context (RepoContext from RepoContextBuilder) is provided,
    the README excerpt is injected into biz_ctx so every enrichment call
    has access to the primary product intent signal.

    Returns the enriched biz_ctx dict.
    """
    if not llm_json_call or not os.environ.get("OPENAI_API_KEY"):
        print("[BRD ENRICHMENT] No API key or client — skipping enrichments.")
        return biz_ctx

    # Inject README excerpt from repo_context into biz_ctx so all 7 calls can use it
    if repo_context and not biz_ctx.get("readme_excerpt"):
        signals = repo_context.get("intent_signals", {})
        readme  = signals.get("readme", "")[:2000].strip()
        if readme:
            biz_ctx["readme_excerpt"] = readme
            print(f"[BRD ENRICHMENT] README injected ({len(readme)} chars) into enrichment context.")

    frs  = fr_dict.get("functional_requirements", [])
    nfrs = nfr_dict.get("non_functional_requirements", [])
    tech = biz_ctx.get("tech_stack", [])
    system_type = biz_ctx.get("product_type", "Software System")

    # Glossary accumulator — deduped across all calls
    all_glossary: Dict[str, str] = {}

    def _collect(result: Dict) -> None:
        for item in result.get("glossary_terms", []):
            t, d = item.get("term", ""), item.get("plain_definition", "")
            if t and d and t not in all_glossary:
                all_glossary[t] = d

    # 1. Executive Summary
    print("[BRD ENRICHMENT] 1/7 — Executive Summary...")
    r = enrich_executive_summary(biz_ctx, features, frs)
    if r.get("executive_summary"):
        biz_ctx["enriched_exec_summary"] = r["executive_summary"]
        _collect(r)

    # 2. Business Context
    print("[BRD ENRICHMENT] 2/7 — Business Context...")
    r = enrich_business_context(biz_ctx, features)
    if r.get("problem_statement"):
        biz_ctx["enriched_problem_statement"] = r.get("problem_statement", "")
        biz_ctx["enriched_goals"]             = r.get("goals", [])
        biz_ctx["enriched_in_scope"]          = r.get("in_scope", [])
        biz_ctx["enriched_out_of_scope"]      = r.get("out_of_scope", [])
        _collect(r)

    # 3. Stakeholders
    print("[BRD ENRICHMENT] 3/7 — Stakeholders...")
    r = enrich_stakeholders(biz_ctx, features, tech)
    if r.get("stakeholders"):
        biz_ctx["enriched_stakeholders"] = r.get("stakeholders", [])
        biz_ctx["enriched_personas"]     = r.get("personas", [])
        _collect(r)

    # 4. Functional Requirements
    print("[BRD ENRICHMENT] 4/7 — Functional Requirements...")
    r = enrich_functional_requirements(frs, features)
    if r.get("enriched_frs"):
        biz_ctx["enriched_frs"] = {item["id"]: item for item in r["enriched_frs"]}
        _collect(r)

    # 5. NFR SLAs
    print("[BRD ENRICHMENT] 5/7 — NFR SLAs...")
    r = enrich_nfrs(nfrs, system_type, tech)
    if r.get("enriched_nfrs"):
        biz_ctx["enriched_nfrs"] = {item["id"]: item for item in r["enriched_nfrs"]}
        _collect(r)

    # 6. Delivery Roadmap
    print("[BRD ENRICHMENT] 6/7 — Delivery Roadmap...")
    r = enrich_roadmap(features, frs)
    if r.get("phases"):
        biz_ctx["enriched_roadmap"] = r["phases"]
        _collect(r)

    # 7. Open Issues
    print("[BRD ENRICHMENT] 7/7 — Open Issues...")
    r = enrich_open_issues(features, biz_ctx)
    if r.get("issues"):
        biz_ctx["enriched_open_issues"] = r["issues"]
        _collect(r)

    biz_ctx["glossary_terms"] = all_glossary
    print(f"[BRD ENRICHMENT] ✅ Complete. Glossary: {len(all_glossary)} terms collected.")
    return biz_ctx
