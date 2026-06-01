# Deterministic Pipeline SOP

> **Last updated:** 2026-05-30
> **Version:** 2.4 — Hybrid Language Registry (Stage 1.2 UnknownLanguageResolver)

## Overview

This document is the Standard Operating Procedure for the Analyst Agent pipeline. It covers the full flow from ingesting a GitHub repository through to producing a validated BRD (`.md` + `.docx`). The pipeline is **deterministic-first** — all structural analysis is rule-based. LLM is used selectively in optional, non-blocking stages.

If `OPENAI_API_KEY` is not set, all LLM stages are silently skipped and the pipeline produces a valid deterministic BRD.

---

## Process Flow

### Phase 1 — Context Extraction

| Stage | Module | Input | Output |
|-------|--------|-------|--------|
| **[1] RepoScanner** | `app/eca/repo_scanner.py` | `repo_url` | `{repo_name, root_path, files[]}` |
| **[2] FileClassifier** | `app/eca/file_classifier.py` | scan output | `{classified_files[{path, category, confidence}]}` |
| **[1.2] UnknownLanguageResolver** | `app/eca/unknown_language_resolver.py` | `classified_data`, repo dir | Writes to `_llm_inferred` block; calls `reload_registry()` |
| **[3] ContentProcessor** | `app/eca/content_processor.py` | classified files + repo path | `{chunks[{chunk_id, file_path, category, content}]}` |
| **[3.1] Sub-Extractors** | `app/eca/extractor.py` (orchestrator) | repo path | `{api_endpoints, entities, dependencies, defects}` |
| **[3.5] RepoContextBuilder** | `app/eca/repo_context_builder.py` | chunks + deps + evidence | `RepoContext` dict |
| **[3.6] EvidenceManifest** | `app/eca/evidence_manifest.py` | repo dir + extractor outputs | `RepoEvidenceManifest` |
| **[4] ContextAggregator → Normalizer → Validator** | `app/context/` | chunks | `{normalized_modules[], score, valid}` |

### Stage 1.1 — Language Registry (`language_registry.json`)

The single source of truth for all language knowledge. Two-tier structure (v1.1):

| Block | Author | Priority |
|---|---|---|
| `"languages"` | Human-curated | **Highest** — always wins on extension collision |
| `"_llm_inferred"` | UnknownLanguageResolver (Stage 1.2) | Lower — fills gaps only |

Rule: `language_loader.py` reads both blocks. Curated entries can never be overwritten by LLM inferences.

### Stage 1.2 — UnknownLanguageResolver (Learn & Cache)

**Triggers:** After FileClassifier (Stage 2) if `OPENAI_API_KEY` is set.
**Non-blocking:** Any failure is caught; pipeline always continues.

Algorithm:
1. Collect all `"unknown"` files from `classified_data`; deduplicate by extension.
2. Check `_llm_inferred` block — skip cached extensions (zero LLM calls on repeat runs).
3. Extract first 800 chars of one representative file per extension.
4. Send one batched LLM call for all remaining unknowns.
5. Accept results with `confidence ≥ 0.7`; reject below threshold.
6. Atomically write accepted results to `language_registry.json → _llm_inferred`.
7. Call `reload_registry()` so the current run benefits immediately.

Anti-hallucination guardrails:
- Bounded candidate list (all known languages given to LLM)
- Evidence citation required (LLM must quote an identifying token)
- Confidence threshold gate (< 0.7 rejected)
- `temperature=0` enforced
- Curated-wins rule (cannot overwrite `"languages"` entries)

---

### Phase 1.5 — Skill Pack Activation

| Stage | Module | Output |
|-------|--------|--------|
| **[4.5] SkillPackMatcher** | `app/skills/skill_matcher.py` | `List[SkillActivation]` |
| **[4.7] SkillPackExecutor** | `app/skills/skill_executor.py` | `SkillExecutionResult` |

Fallback: If no pack scores ≥ 0.5 and `OPENAI_API_KEY` is set, `SkillComposer` auto-generates a new pack.

---

### Phase 2 — Analysis & Feature Extraction

| Stage | Module | Output |
|-------|--------|--------|
| **[5] FeatureExtractionAgent** | `app/analysis/feature_extraction_agent.py` | `{features[ExtractedFeature]}` |
| **[6] FeatureValidator** | `app/analysis/feature_validator.py` | `{validated_features[ValidatedFeature]}` |
| **[6.5] Semantic Pruning** *(LLM, optional)* | `app/utils/llm_enrichment.py` | Filtered features |

---

### Phase 3 — Requirement Generation

| Stage | Module | Output |
|-------|--------|--------|
| **[7] ProductUnderstandingAgent** | `app/analysis/product_understanding_agent.py` | `ProductUnderstandingResult` |
| **[8] FunctionalRequirementGenerator** | `app/analysis/functional_requirement_generator.py` | `FunctionalRequirementsResult` |
| **[9] NonFunctionalRequirementGenerator** | `app/analysis/non_functional_requirement_generator.py` | `NonFunctionalRequirementsResult` |
| **[3.5L] LLM Enrichment** *(optional)* | `app/utils/llm_enrichment.py` | Enriched features + core_value |
| **[3.6L] BusinessUnderstandingAgent** | `app/analysis/business_understanding_agent.py` | `BusinessUnderstandingResult` |
| **[3.7] BRDEnrichmentAgent** *(optional, 7 LLM calls)* | `app/analysis/brd_enrichment_agent.py` | Enriched `biz_ctx` |

---

### Phase 4 — BRD Composition & Validation

| Stage | Module | Output |
|-------|--------|--------|
| **[10a] BRDComposer** | `app/analysis/brd_composer.py` | 16-section Markdown BRD |
| **[10b] BRDValidator** *(9 dimensions, threshold 0.85)* | `app/analysis/brd_validator.py` | `{score, issues[], needs_revision}` |
| **[10c] BRDFixLoop** *(max 2 iterations)* | `app/analysis/brd_fix_loop.py` | `{final_markdown, final_validation, iterations}` |

---

### Phase 5 — Export

| Stage | Module | Output |
|-------|--------|--------|
| **DocumentGenerator** | `app/analysis/document_generator.py` | `BRD_<repo_name>.md` + `BRD_<repo_name>.docx` |

---

## Conversion Layer (Deterministic MinimalBRD, no LLM)

**Input:** `final_payload.json`  
**Module:** `app/analysis/payload_converter.py`

**Sub-stages (all rule-based, no LLM):**

1. `extract_features(payload)` — Derives one `AnalysisFeature` per normalized module + a meta-feature from validation score.
2. `derive_requirements(features)` — Produces one SHALL-style `Requirement` per feature.
3. `build_brd(payload)` — Assembles a `MinimalBRD` from the three sub-outputs.

**Output:** `MinimalBRD` (see `app/schemas/models.py`)
```json
{
  "repo_name": "string",
  "summary": "string",
  "validation_score": 0.0,
  "validation_passed": true,
  "features": [{"id", "name", "confidence", "sources", "category"}],
  "requirements": [{"id", "feature_id", "description", "priority", "source_modules"}],
  "gaps": ["string"],
  "modules_detected": ["string"]
}
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe |
| POST | `/analyze` | Phase 1 only; returns `final_payload` |
| POST | `/convert` | Convert pre-computed payload → `MinimalBRD` |
| POST | `/analyze-and-convert` | Full pipeline + BRD in one call |

---

## Error Handling & Reliability

| Scenario | Behavior |
|----------|----------|
| No `OPENAI_API_KEY` | All LLM stages silently skipped — including Stage 1.2. Full deterministic output. |
| Stage 1.2 failure | Caught; logged; pipeline continues. File stays `"unknown"`. |
| Unknown extension in `_llm_inferred` | Static lookup on all subsequent runs — zero LLM calls. |
| LLM call fails | `_safe_call()` returns `{}`. Deterministic templates used. |
| RepoScanner failure | `RuntimeError` raised immediately. Pipeline stops. |
| Missing README | `RepoContextBuilder` waterfall falls to `[NO_DOCUMENTATION]`. |
| BRD score < 0.85 | `BRDFixLoop` applies up to 2 repair passes and re-validates. |
| API endpoint exception | `HTTPException(500)` + `traceback.print_exc()`. |

---

## Self-Annealing Rule

When any error or quality failure occurs:
1. **Analyze** — identify root cause
2. **Patch** — apply targeted fix
3. **Test** — run `pytest app/tests/ -v`
4. **Update SOP** — update this file before committing code changes

Confidence values are **never inflated** beyond what the source data provides.
