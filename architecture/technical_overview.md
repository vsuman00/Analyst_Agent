# Analyst-Agent Technical Overview

> **Last updated:** 2026-05-20
> **See also:** [Architecture.md](../Architecture.md) for full detailed reference.

This document provides a concise overview of the Analyst-Agent's architecture, the deterministic data extraction pipeline, and the core functions of its components.

---

## A.N.T. 3-Layer Architecture

The Analyst-Agent follows the **A.N.T. (Architecture, Navigation, Tools)** 3-Layer Architecture to ensure reliability, maintainability, and deterministic behavior.

### Layer 1: Architecture (`architecture/`)
- **Role**: The "source of truth" for technical standards and procedures.
- **Components**: Contains Standard Operating Procedures (SOPs) and documentation (like this file).
- **Invariant**: If logic changes, the SOP must be updated before the code.

### Layer 2: Navigation (`app/api/`, `app/pipeline/`)
- **Role**: The reasoning and coordination layer.
- **Components**:
    - **API** (`app/api/main.py`): Handles external requests via 15 FastAPI routes.
    - **Pipeline Runner** (`app/pipeline/runner.py`): Three public functions that share a single orchestration core.
- **Constraint**: This layer manages flow but does not perform complex data transformations directly.

### Layer 3: Tools (`app/eca/`, `app/context/`, `app/analysis/`, `app/utils/`)
- **Role**: The deterministic execution layer.
- **Components**: Atomic, testable Python scripts. Core logic is deterministic; LLM is optional enrichment.
- **Constraint**: Every LLM call has a working deterministic fallback.

---

## Pipeline Runner Functions

All three public functions in `app/pipeline/runner.py`:

| Function | Scope | Used By |
|----------|-------|---------|
| `run_full_pipeline_service(repo_url, output_dir)` | All 10 stages — returns full result dict | `run_end_to_end()`, `/analyze-and-convert` API |
| `run_end_to_end(repo_url, output_dir)` | CLI wrapper — calls `run_full_pipeline_service()`, writes BRD to disk | CLI `__main__` |
| `run_pipeline(repo_url, output_path)` | Phase 1 only — clone → scan → classify → chunk → normalize | `/analyze` API endpoint |

---

## Full Pipeline Stages

### Phase 1 — Context Extraction

| Stage | Module | Output |
|-------|--------|--------|
| **[1] RepoScanner** | `app/eca/repo_scanner.py` | `{repo_name, root_path, files[]}` |
| **[2] FileClassifier** | `app/eca/file_classifier.py` | `{classified_files[{path, category, confidence}]}` |
| **[3] ContentProcessor** | `app/eca/content_processor.py` | `{chunks[{chunk_id, file_path, category, content}]}` |
| **[3.5] RepoContextBuilder** | `app/eca/repo_context_builder.py` | `RepoContext` dict — README, tech_stack, key_snippets |
| **[3.6] EvidenceManifest** | `app/eca/evidence_manifest.py` | `RepoEvidenceManifest` — has_docker, has_kubernetes, platform, etc. |
| **[4] ContextAggregator → Normalizer → Validator** | `app/context/` | `{normalized_modules[], score, valid}` |

**RepoContextBuilder intent signal waterfall:**
```
1. README.md / readme.md / README.rst
2. package.json (description + keywords)
3. pyproject.toml / Cargo.toml / go.mod
4. Top-level docstring of main.py / app.py / index.ts
5. [NO_DOCUMENTATION] — signals LLM to lower confidence
```

### Phase 2 — Analysis & Feature Extraction

| Stage | Module | Output |
|-------|--------|--------|
| **[5] FeatureExtractionAgent** | `app/analysis/feature_extraction_agent.py` | `{features[ExtractedFeature]}` |
| **[6] FeatureValidator** | `app/analysis/feature_validator.py` | `{validated_features[ValidatedFeature]}` |
| **[6.5] Semantic Pruning** *(LLM, optional)* | `app/utils/llm_enrichment.py` | Filtered `validated_features` |

### Phase 3 — Requirement Generation

| Stage | Module | Output |
|-------|--------|--------|
| **[7] ProductUnderstandingAgent** | `app/analysis/product_understanding_agent.py` | `ProductUnderstandingResult` |
| **[8] FunctionalRequirementGenerator** | `app/analysis/functional_requirement_generator.py` | `FunctionalRequirementsResult` |
| **[9] NonFunctionalRequirementGenerator** | `app/analysis/non_functional_requirement_generator.py` | `NonFunctionalRequirementsResult` |
| **[3.5] LLM Feature Enrichment** *(optional)* | `app/utils/llm_enrichment.py` | Enriched features + core_value |
| **[3.6] BusinessUnderstandingAgent** | `app/analysis/business_understanding_agent.py` | `BusinessUnderstandingResult` |
| **[3.7] BRDEnrichmentAgent** *(optional, 7 LLM calls)* | `app/analysis/brd_enrichment_agent.py` | Enriched `biz_ctx` for all BRD sections |

### Phase 4 — BRD Composition & Validation

| Stage | Module | Output |
|-------|--------|--------|
| **[10a] BRDComposer** | `app/analysis/brd_composer.py` | 16-section Markdown BRD |
| **[10b] BRDValidator** | `app/analysis/brd_validator.py` | `{score, issues[], needs_revision}` |
| **[10c] BRDFixLoop** *(max 2 iterations)* | `app/analysis/brd_fix_loop.py` | `{final_markdown, final_validation, iterations}` |

### Phase 5 — Export

| Stage | Module | Output |
|-------|--------|--------|
| **DocumentGenerator** | `app/analysis/document_generator.py` | `BRD_<repo_name>.md` + `BRD_<repo_name>.docx` |

---

## BRD Validation (9 Dimensions)

| # | Dimension | What is Checked |
|---|-----------|----------------|
| 1 | **Completeness** | All 16 required section headings present |
| 2 | **Traceability** | Every input feature name and FR-ID in BRD |
| 3 | **No-Hallucination** | No phantom FR-IDs in the BRD |
| 4 | **Clarity** | No banned vague phrases |
| 5 | **FR Testability** | FR lines contain testable verbs (SHALL, MUST, etc.) |
| 6 | **NFR Specificity** | NFR SLAs have real values (not TBD/Strict) |
| 7 | **Stakeholder Specificity** | Roles are project-specific (not "End User") |
| 8 | **Section Depth** | Every section ≥ 30 words (Exec Summary ≥ 60) |
| 9 | **Tech Grounding** | Tech claims backed by `RepoEvidenceManifest` |

**Pass threshold:** score ≥ 0.85

---

## Core Data Schemas

All Pydantic models are in `app/schemas/models.py`.

### ECA Output Schema
```json
{
  "readme": "string",
  "file_tree": { "dir": { "file.py": null } },
  "classified_files": {
    "frontend": [], "backend": [], "config": [], "docs": [], "unknown": []
  },
  "chunks": [ { "file": "string", "content": "string" } ]
}
```

### Normalized Context Schema
```json
{
  "normalized_modules": [
    { "id": "uuid5", "name": "snake_case_module", "files": ["string"], "confidence": 0.9 }
  ]
}
```

### RepoEvidenceManifest (key fields)
```json
{
  "platform": "android|ios|desktop|web|server|library|unknown",
  "has_http_api": true,
  "has_grpc": false,
  "has_docker": true,
  "has_kubernetes": false,
  "has_android": false,
  "has_auth": true,
  "has_database": true,
  "has_gdpr_mention": false,
  "primary_language": "python",
  "build_tool": "pip"
}
```

---

## Language & Archetype Registries

All language knowledge lives in `app/eca/config/language_registry.json`.
All product archetypes live in `app/analysis/config/archetype_registry.json`.

**Zero Python changes required to add a new language or archetype** — edit the JSON file only.

- **40+ languages registered:** Python, JavaScript, TypeScript, Java, Kotlin, Go, Rust, Swift, C#, and more.
- **13 archetypes registered:** api_backend_service, social_platform, data_platform, mobile_app, ml_ai_platform, and more.

---

## Error Handling Summary

| Scenario | Behavior |
|----------|----------|
| No `OPENAI_API_KEY` | All LLM phases silently skipped. Full deterministic output. |
| LLM call fails | `_safe_call()` returns `{}`. BRDComposer uses deterministic templates. |
| RepoScanner failure | `RuntimeError` raised immediately. Pipeline stops. |
| Missing README | `RepoContextBuilder` waterfall falls to `[NO_DOCUMENTATION]`. |
| BRD score < 0.85 | `BRDFixLoop` applies up to 2 repair passes and re-validates. |
| Unknown file extension | `language_loader.py` returns `"unknown"` role; file still processed. |
| API endpoint exception | `HTTPException(500)` + `traceback.print_exc()`. |
