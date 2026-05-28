# Architecture — Analyst Agent

> **Last updated:** 2026-05-28  
> **Version:** 2.3 — Dynamic Skill Pack system + 9-dimension BRD validator + GPT-5/o-series support

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [3-Layer Architecture (A.N.T.)](#2-3-layer-architecture-ant)
3. [Full Pipeline Workflow](#3-full-pipeline-workflow)
4. [Pipeline State Machine](#4-pipeline-state-machine)
5. [Module Reference](#5-module-reference)
6. [Dynamic Skill Pack System](#6-dynamic-skill-pack-system)
7. [Data Flow & Pydantic Schemas](#7-data-flow--pydantic-schemas)
8. [LLM Integration Points](#8-llm-integration-points)
9. [API Endpoints](#9-api-endpoints)
10. [Configuration Reference](#10-configuration-reference)
11. [Error Handling Patterns](#11-error-handling-patterns)
12. [Design Principles](#12-design-principles)
13. [Directory Structure](#13-directory-structure)

---

## 1. System Overview

**Analyst Agent** is an enterprise-grade backend system that converts any public GitHub repository into a comprehensive, validated Business Requirement Document (BRD).

```
GitHub Repository URL  ──►  Analyst Agent Pipeline  ──►  BRD (.md / .docx)
```

**Core capabilities:**
- Clone and scan any public GitHub repository
- Classify files by language and role using a data-driven registry (40+ languages)
- Extract features, entities, API routes, dependencies, and defect signals
- Dynamically activate domain-specific skill packs for specialized analysis
- Generate testable functional and non-functional requirements
- Compose a validated 16-section enterprise BRD
- Export to Markdown or Word (`.docx`)

**Execution modes:**
- **CLI** — `python -m app.pipeline.runner <repo_url>` (full end-to-end)
- **API** — `uvicorn app.api.main:app` (FastAPI, ~20 endpoints)
- **Deterministic-only** — runs without `OPENAI_API_KEY`; LLM phases silently skipped

---

## 2. 3-Layer Architecture (A.N.T.)

The system follows a strict three-layer separation of concerns:

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1 — ARCHITECTURE  (architecture/)                        │
│  Technical SOPs in Markdown. Updated before code changes.       │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 2 — NAVIGATION  (app/pipeline/)                          │
│  Orchestration layer. Routes data between tools.                │
│  No complex logic performed directly.                           │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 3 — TOOLS  (app/)                                        │
│  Deterministic Python scripts. Atomic, Pydantic-validated,      │
│  and independently testable. Each has a CLI __main__ entry.     │
└─────────────────────────────────────────────────────────────────┘
```

**Key rule:** Logic lives in Tools. Navigation only calls Tools and passes data between them. Architecture documents what Tools do before they are changed.

---

## 3. Full Pipeline Workflow

### 3.1 End-to-End Flow Diagram

```
GitHub Repo URL
       │
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 1 — CONTEXT EXTRACTION                                       │
│                                                                     │
│  [1] RepoScanner                                                    │
│       git clone → os.walk (binary/ignore filtered)                 │
│       Output: {repo_name, root_path, files[{path, ext, size}]}     │
│       │                                                             │
│  [2] FileClassifier                                                 │
│       Path heuristics + language_registry.json role lookup         │
│       Output: {classified_files[{path, category, confidence}]}     │
│       │                                                             │
│  [3] ContentProcessor                                               │
│       Line-by-line read, chunk at ~3200 chars, UUID chunk_ids      │
│       Output: {chunks[{chunk_id, file_path, category, content}]}   │
│       │                                                             │
│  [3.5] RepoContextBuilder  ◄── Priority waterfall:                 │
│       README → package.json → pyproject.toml → Cargo.toml         │
│       → entry point docstring → [NO_DOCUMENTATION]                 │
│       Output: {intent_signals, tech_stack, structure,              │
│                key_file_snippets, no_readme, confidence_note}      │
│       │                                                             │
│  [3.6] EvidenceManifest                                             │
│       APIExtractor + DependencyExtractor + EntityExtractor         │
│       + file system scan                                           │
│       Output: RepoEvidenceManifest (has_http_api, has_docker,      │
│               has_android, has_kubernetes, dep_categories, ...)    │
│       │                                                             │
│  [4] ContextAggregator → ContextNormalizer → ContextValidator      │
│       Chunks → modules by top-level dir → snake_case dedup         │
│       Output: {normalized_modules[{id, name, files[], confidence}]}│
└─────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 1.5 — SKILL PACK ACTIVATION                                  │
│                                                                     │
│  [4.5] SkillPackMatcher                                             │
│        Loads all SKILL.md files from app/skills/packs/              │
│        Scores each pack against RepoEvidenceManifest + deps using   │
│        max-of-dimensions algorithm (threshold: 0.5)                 │
│        Falls back to SkillComposer (LLM) if no pack matches        │
│        Output: List[SkillActivation] — top scoring packs            │
│        │                                                            │
│  [4.7] SkillPackExecutor                                            │
│        Runs each activated pack's scripts as isolated subprocesses  │
│        Collects domain features, signals, and BRD section hints     │
│        All failures non-blocking (try/except per pack)              │
│        Output: SkillExecutionResult                                 │
└─────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 2 — ANALYSIS & FEATURE EXTRACTION                            │
│                                                                     │
│  [5] FeatureExtractionAgent                                         │
│       PRIMARY: LLM with RepoContext (README + structure + snippets) │
│       + skill_results injected into LLM prompt as additional context│
│       + skill features merged (deduped by name similarity) first    │
│       FALLBACK: Module names as generic features                    │
│       Post-process: cross-file confidence boost + negative penalty  │
│       Output: {features[{id, name, description,                     │
│                           source_modules[], confidence}]}           │
│       │                                                             │
│  [6] FeatureValidator                                               │
│       Pass 1: Exact-name deduplication (max-pool confidence)       │
│       Pass 2: MERGE_GROUPS overlap merging                         │
│       Pass 3: snake_case normalisation + re-index IDs              │
│       Output: {validated_features[{id, name, description,          │
│                                    confidence, merge_of[]}]}       │
│       │                                                             │
│  [6.5] Semantic Feature Pruning  (LLM, optional)                   │
│       prune_hallucinated_features() — README as ground truth       │
│       Returns subset of validated_features with false positives    │
│       removed                                                       │
└─────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 3 — REQUIREMENT GENERATION                                   │
│                                                                     │
│  [7] ProductUnderstandingAgent                                      │
│       PRIMARY: LLM archetype detection (evidence block highest     │
│                priority signal)                                     │
│       FALLBACK: archetype_registry.json keyword voting             │
│       Output: {product: {name, summary, core_capabilities[]}}      │
│       │                                                             │
│  [8] FunctionalRequirementGenerator                                 │
│       Priority: template match → LLM generation → deterministic    │
│       1–3 FRs per feature (based on confidence)                    │
│       Output: {functional_requirements[{id, description,           │
│                linked_feature, acceptance_criteria[]}]}            │
│       │                                                             │
│  [9] NonFunctionalRequirementGenerator                              │
│       Keyword-triggered template selection (max 8 NFRs)            │
│       Output: {non_functional_requirements[{id, category, desc}]}  │
│       │                                                             │
│  [3.5L] LLM Enrichment  (optional, requires OPENAI_API_KEY)        │
│       enrich_features() — rewrite descriptions as SHALL-style      │
│       enrich_core_value() — ≤30-word value statement               │
│       enrich_enterprise_artifacts() — stakeholders, CI/CD, infra,  │
│                                       data, compliance, risks      │
│       │                                                             │
│  [3.6L] BusinessUnderstandingAgent                                  │
│       Keyword voting → {product_type, primary_users, core_value}   │
│       │                                                             │
│  [3.7] BRDEnrichmentAgent  (optional, 7 LLM calls)                 │
│       1. Executive Summary    5. NFR SLAs                          │
│       2. Business Context     6. Delivery Roadmap                  │
│       3. Stakeholders         7. Open Issues                       │
│       4. Functional Reqs (batched, 8 FRs/call)                     │
│       Accumulates glossary terms across all calls                  │
└─────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 4 — BRD COMPOSITION & VALIDATION                             │
│                                                                     │
│  [10a] BRDComposer                                                  │
│        16-section Markdown assembly                                 │
│        Each section: LLM-enriched path (from biz_ctx enriched      │
│        fields) with deterministic fallback                          │
│        Evidence-aware: checks RepoEvidenceManifest before writing  │
│        platform/infra/compliance claims                             │
│        Output: initial_markdown (string)                           │
│        │                                                            │
│  [10b] BRDValidator (9 dimensions, threshold 0.85)                 │
│        1. Completeness      6. NFR Specificity                     │
│        2. Traceability      7. Stakeholder Specificity             │
│        3. No-Hallucination  8. Section Depth                       │
│        4. Clarity           9. Tech Grounding                      │
│        5. FR Testability                                            │
│        Output: {score, issues[], needs_revision}                   │
│        │                                                            │
│  [10c] BRDFixLoop  (max 2 iterations)                              │
│        If score < 0.85: _apply_fixes() → re-validate               │
│        Fixes: vague language removal, missing section stubs,       │
│               storytelling intro removal                           │
│        Output: {final_markdown, final_validation, iterations}      │
└─────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 5 — EXPORT                                                   │
│                                                                     │
│  DocumentGenerator                                                  │
│       Markdown → .docx via python-docx                             │
│       Handles: tables, H1/H2/H3, bullets, inline markup, HR        │
│       Output: BRD_<repo_name>.md + BRD_<repo_name>.docx            │
│               saved to runtime/pipeline_out/<repo_name>/brd/       │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Two Execution Paths

**Path A — CLI (`run_end_to_end`)**

All stages run sequentially in `app/pipeline/runner.py`. Delegates to `run_full_pipeline_service()` for the shared orchestration core. Colored stage logging. Writes `BRD_<repo_name>.md` to `runtime/pipeline_out/<repo_name>/brd/`.

```bash
python -m app.pipeline.runner https://github.com/owner/repo --outdir runtime/pipeline_out
```

**Path B — API (`/analyze-and-convert`)**

`run_full_pipeline_service()` handles all stages end-to-end — **not** `run_pipeline()`. The endpoint returns `{pipeline, brd, markdown, validation}`. The separate `/analyze` endpoint uses `run_pipeline()` for Phase 1 only.

```bash
POST /analyze-and-convert  {"repo_url": "https://github.com/owner/repo"}
```

**Function responsibilities in `runner.py`:**

| Function | Scope | Used By |
|---|---|---|
| `run_full_pipeline_service(repo_url, output_dir)` | All stages — returns full result dict | `run_end_to_end()`, `/analyze-and-convert` |
| `run_end_to_end(repo_url, output_dir)` | CLI wrapper — calls `run_full_pipeline_service()`, writes BRD to disk | CLI `__main__` |
| `run_pipeline(repo_url, output_path)` | Phase 1 only — clone → scan → classify → chunk → normalize | `/analyze` endpoint |

---

## 4. Pipeline State Machine

```
                    ┌─────────┐
                    │ CREATED │
                    └────┬────┘
                         │ run_end_to_end() / run_full_pipeline_service() called
                         ▼
                   ┌──────────┐
                   │INGESTING │  RepoScanner cloning + scanning
                   └────┬─────┘
                         │ scan complete
                         ▼
                   ┌──────────┐
                   │ ECA_DONE │  FileClassifier + ContentProcessor done
                   └────┬─────┘
                         │
                         ▼
                 ┌───────────────┐
                 │ CONTEXT_READY │  RepoContextBuilder + EvidenceManifest done
                 └──────┬────────┘
                         │
                         ▼
                  ┌────────────┐
                  │ NORMALIZED │  ContextAggregator + Normalizer done
                  └─────┬──────┘
                         │
                         ▼
                  ┌────────────┐
                  │ VALIDATED  │  ContextValidator scored
                  └─────┬──────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  SKILLS_ACTIVATED    │  SkillPackMatcher + Executor done
              └──────────┬───────────┘
                         │
                         ▼
                  ┌────────────┐
                  │  ANALYZED  │  FeatureExtraction + Validation done
                  └─────┬──────┘
                         │
              ┌──────────┴──────────┐
              │ OPENAI_API_KEY set? │
              └──────────┬──────────┘
           YES ◄──────────┘──────────► NO
            │                          │
            ▼                          │
    ┌──────────────┐                   │
    │ LLM_ENRICHED │  Prune + Enrich   │
    └──────┬───────┘                   │
            └──────────┬───────────────┘
                        ▼
                  ┌───────────┐
                  │ BRD_READY │  BRDComposer assembled initial Markdown
                  └─────┬─────┘
                         │
                         ▼
                  ┌────────────┐
                  │ VALIDATING │  BRDValidator scoring (9 dimensions)
                  └─────┬──────┘
                         │
              ┌──────────┴──────────┐
              │   score >= 0.85?    │
              └──────────┬──────────┘
           YES ◄──────────┘──────────► NO (max 2 iterations)
            │                          │
            │                          ▼
            │                   ┌────────────┐
            │                   │ IMPROVING  │  BRDFixLoop patches applied
            │                   └─────┬──────┘
            │                         │ re-validate
            │                         ▼
            │                   ┌────────────┐
            │                   │ VALIDATING │  (loop back)
            │                   └────────────┘
            │
            ▼
      ┌───────────┐
      │ COMPLETED │  BRD written to disk
      └───────────┘

  On any unhandled exception:
      → FAILED  (RuntimeError raised, traceback printed, sys.exit(1))
```

---

## 5. Module Reference

### 5.1 ECA Layer (`app/eca/`)

| Module | Function | Input | Output |
|--------|----------|-------|--------|
| `repo_scanner.py` | `scan_repository(repo_url, dest_dir, skip_clone)` | GitHub URL + dest path | `{repo_name, root_path, files[]}` |
| `file_classifier.py` | `run_classifier(scan_output)` | scan output | `{classified_files[{path, category, confidence}]}` |
| `content_processor.py` | `run_content_processor(classified_data, repo_dir)` | classified files + repo path | `{chunks[{chunk_id, file_path, category, content}]}` |
| `language_loader.py` | `get_role(ext)`, `get_language(ext)`, `is_binary(ext)`, `is_entry_point(filename)` | file extension / name | role string / bool |
| `extractor.py` | `extract_eca(repo_path)` | repo path | `ECAOutput` Pydantic model |
| `api_extractor.py` | `extract_api_endpoints(repo_dir)` | repo path | `{endpoints[], grpc_rpcs[]}` |
| `entity_extractor.py` | `extract_entities(repo_dir)` | repo path | `{entities[{name, source_file, table_name, fields[], entity_type}]}` |
| `dependency_extractor.py` | `extract_dependencies(repo_dir)` | repo path | `{dependencies[], build_tool, language, uses_jcenter}` |
| `defect_extractor.py` | `extract_defects(repo_dir)` | repo path | `{defects[{id, type, severity, file, line, description}]}` |
| `repo_context_builder.py` | `build_repo_context(repo_root, chunks_data, dep_data, evidence)` | repo path + chunks + deps + evidence | `RepoContext` dict |
| `evidence_manifest.py` | `build_evidence_manifest(repo_dir, api_data, dep_data)` | repo path + extractor outputs | `RepoEvidenceManifest` dict |

**`FileClassifier` category hierarchy (priority order):**
```
entry_point → config → route → service → component → unknown
```

**`RepoContextBuilder` intent signal waterfall:**
```
1. README.md / readme.md / README.rst / README.txt
2. package.json (description + keywords + name)
3. pyproject.toml [tool.poetry] or [project]
4. Cargo.toml [package]
5. go.mod + top-level .go file comment
6. Top-level docstring of main.py / app.py / index.ts / server.js
7. [NO_DOCUMENTATION] — signals LLM to lower confidence
```

### 5.2 Context Layer (`app/context/`)

| Module | Function | Input | Output |
|--------|----------|-------|--------|
| `aggregator.py` | `aggregate_context(chunks_data)` | chunks | `{modules[{module_name, files[], chunk_ids[]}]}` |
| `normalizer.py` | `normalize_context(aggregated_data)` | aggregated modules | `{normalized_modules[{id, name, files[], confidence}]}` |
| `validator.py` | `validate_context(normalized_data)` | normalized modules | `{score, issues[], valid}` |

**Normalizer noise filter** — removes these top-level dirs:
`.idea`, `.vscode`, `.git`, `.gradle`, `.github`, `.husky`, `node_modules`, `build`, `dist`, `out`, `target`, `bin`, `obj`, `vendor`, `tmp`, `temp`, `logs`, `coverage`, `__pycache__`

### 5.3 Skills Layer (`app/skills/`)

| Module | Function | Input | Output |
|--------|----------|-------|--------|
| `skill_loader.py` | `load_all_skills()` | packs directory (auto) | `List[SkillPack]` — parsed SKILL.md metadata |
| `skill_matcher.py` | `detect_skill_packs(evidence, repo_context, dep_data)` | repo evidence + context + deps | `List[Tuple[SkillPack, float]]` — scored matches above threshold |
| `skill_executor.py` | `execute_skill_packs(activated_packs, repo_path)` | activated packs + repo path | `SkillExecutionResult` — features + signals + hints |
| `skill_composer.py` | `compose_missing_skill(evidence, repo_context, deps)` | evidence + context + deps | generated `SkillPack` written to `packs/_generated/` |

**SKILL.md YAML Frontmatter Schema:**
```yaml
name: web_api
display_name: Web API Pack
description: REST/gRPC endpoint extraction and contract analysis
version: 1.0.0
author: system
detection_signals:
  evidence_flags: [has_http_api, has_grpc]
  dependency_keywords: [fastapi, flask, django, express, spring]
  file_patterns: ["**/routes/**", "**/*.proto"]
scripts:
  - name: api_extractor
    path: scripts/api_extractor.py
    args: [--repo-path, "{repo_path}", --mode, contracts]
brd_hints:
  sections: ["API Contract", "Authentication", "Rate Limiting"]
  focus_areas: ["endpoint cataloguing", "auth flow"]
```

**Scoring Algorithm (max-of-dimensions):**
```
evidence_score = has_matching_flag ? min(1.0, matches * 0.5) : 0.0
dep_score     = match_count == 0 → 0.0 | 1 → 0.6 | 2 → 0.8 | 3+ → 1.0
file_score    = min(1.0, file_matches * 0.4)
final         = max(evidence_score, dep_score, file_score)
              + 0.15 bonus if ≥2 dimensions > 0
```

**Seed Packs (5 included):**

| Pack | Type | Script | Primary Detection |
|------|------|--------|-------------------|
| `web_api` | Script + Instructions | `api_extractor.py` | `has_http_api` / framework deps |
| `ml_pipeline` | Script + Instructions | `model_extractor.py` | ML framework deps / `.ipynb` |
| `data_platform` | Script + Instructions | `pipeline_extractor.py` | `has_database` / orchestrator deps |
| `mobile_app` | Script + Instructions | `screen_extractor.py` | `has_android` / `has_ios` |
| `cli_tool` | Instructions only | — | CLI framework deps |

### 5.4 Analysis Layer (`app/analysis/`)

| Module | Function | Input | Output |
|--------|----------|-------|--------|
| `feature_extraction_agent.py` | `extract_features(modules, chunks, repo_context, skill_results)` | normalized modules + chunks + RepoContext + skill results | `FeatureExtractionResult` |
| `feature_validator.py` | `validate_features(features)` | extracted features | `FeatureValidationResult` |
| `feature_interpretation_agent.py` | `interpret_features(signals)` | raw signals | `FeatureInterpretationResult` |
| `product_understanding_agent.py` | `understand_product(features, repo_context, evidence)` | validated features + context + evidence | `ProductUnderstandingResult` |
| `business_understanding_agent.py` | `understand_business(features, system_type)` | validated features + system type | `BusinessUnderstandingResult` |
| `functional_requirement_generator.py` | `generate_requirements(features)` | validated features | `FunctionalRequirementsResult` |
| `non_functional_requirement_generator.py` | `generate_nfrs(system_type, tech_stack)` | system type + tech stack | `NonFunctionalRequirementsResult` |
| `archetype_loader.py` | `get_domain_signals()` | — | `{archetype_key: {keywords, display, fragment}}` |
| `payload_converter.py` | `build_brd(payload)` | final payload dict | `MinimalBRD` |
| `brd_composer.py` | `compose_brd(biz_ctx, features, frs, nfrs, evidence)` | all analysis outputs | Markdown string |
| `brd_enrichment_agent.py` | `enrich_brd_context(biz_ctx, features, fr_dict, nfr_dict, repo_context)` | all analysis outputs | enriched `biz_ctx` dict |
| `brd_validator.py` | `validate_brd(markdown, features, frs, evidence)` | BRD markdown + inputs | `BRDValidationResult` |
| `brd_fix_loop.py` | `run_fix_loop(markdown, max_iterations, features, frs, evidence)` | initial BRD markdown | `{final_markdown, final_validation, iterations}` |
| `document_generator.py` | `markdown_to_docx(brd_markdown, out_path)` | BRD markdown + output path | `.docx` file |

**`FeatureValidator` merge groups** (hardcoded, extend in `MERGE_GROUPS` dict):
```python
"container_and_cicd_config":                 {container_orchestration_config, ci_cd_pipeline_config}
"authentication_and_credential_management":  {token_based_authentication, secret_credential_management}
"domain_model_and_service_layer":            {domain_entity_modelling, domain_service_layer}
```

**`FunctionalRequirementGenerator` priority chain:**
```
1. FR_TEMPLATES dict match (curated, deterministic)
2. LLM generation grounded in feature evidence
3. _generate_deterministic_requirements() generic fallback
```

### 5.5 Utility Layer (`app/utils/`)

| Module | Function | Purpose |
|--------|----------|---------|
| `llm_client.py` | `llm_json_call(system, user, max_tokens)` | JSON-mode LLM call, returns parsed dict |
| `llm_client.py` | `llm_text_call(system, user, max_tokens)` | Free-text LLM call, returns string |
| `llm_enrichment.py` | `prune_hallucinated_features(features, repo_context)` | Remove false-positive features |
| `llm_enrichment.py` | `enrich_features(features)` | Rewrite descriptions as SHALL-style |
| `llm_enrichment.py` | `enrich_executive_summary(biz_ctx, features)` | Generate ≤120-word exec summary |
| `llm_enrichment.py` | `enrich_core_value(features)` | Generate ≤30-word core value statement |
| `llm_enrichment.py` | `enrich_enterprise_artifacts(biz_ctx, features, tech_stack, evidence)` | Generate stakeholders, CI/CD, infra, data, compliance, risks |

### 5.6 Output Layer (`app/output/`)

| Module | Function | Purpose |
|--------|----------|---------|
| `final_output_builder.py` | `build_final_output(scan, classified, chunks, modules, validation)` | Merge all Phase 1 outputs into canonical payload |

---

## 6. Dynamic Skill Pack System

The Skill Pack system is a **non-blocking, signal-driven intelligence layer** that fires between the Evidence Manifest stage (4) and Feature Extraction stage (5). It follows the same SKILL.md architecture used by Codex, Claude Code, and Antigravity.

### 6.1 How It Works

```
  RepoEvidenceManifest + dependency list
            │
            ▼
  SkillPackMatcher
    ├── Loads all SKILL.md files from app/skills/packs/
    ├── Scores each against evidence using max-of-dimensions
    ├── Returns packs with score ≥ 0.5
    └── If none match → SkillComposer auto-generates one via LLM
            │
            ▼
  SkillPackExecutor  (one per activated pack)
    ├── Reads scripts[] list from pack metadata
    ├── Runs each script as an isolated subprocess (timeout=60s)
    ├── Collects stdout JSON: {features[], signals[], hints[]}
    └── Returns SkillExecutionResult
            │
            ▼
  FeatureExtractionAgent
    ├── Receives skill_results: SkillExecutionResult
    ├── Prepends skill features to extracted features (deduped)
    └── Injects skill signals as additional context into LLM prompt
```

### 6.2 Adding a New Skill Pack

**Step 1** — Create the pack directory:
```
app/skills/packs/my_domain/
├── SKILL.md              ← required
├── scripts/
│   └── extractor.py      ← optional, stdlib only, argparse CLI
└── references/
    └── patterns.md       ← optional reference docs
```

**Step 2** — Write `SKILL.md` with YAML frontmatter (see §5.3 schema above)

**Step 3** — Script contract (if using scripts):
```python
# Must accept --repo-path and --mode args (argparse)
# Must print a single JSON object to stdout:
{
  "features": [{"name": str, "description": str, "confidence": float}],
  "signals":  [{"key": str, "value": any}],
  "hints":    [str]
}
```

**No registration code needed** — `skill_loader.py` auto-discovers all packs on startup.

### 6.3 Auto-Generation (SkillComposer)

When no existing pack scores ≥ 0.5 for a repository:

1. `SkillComposer` computes a fingerprint from `{primary_language, dep_categories, evidence_flags}`
2. Checks `packs/_generated/<fingerprint>.md` (idempotent — same repo type = same pack)
3. If not found: calls LLM to generate SKILL.md content + optional extraction script
4. Writes to `packs/_generated/` for reuse across future runs
5. The generated pack is immediately usable — no restart required

Promotion to stable curated packs:
```bash
PUT /skills/{generated_id}/promote   → moves to packs/{name}/
```

### 6.4 Failure Handling

| Failure Mode | Behavior |
|--------------|----------|
| No pack matches + no OPENAI_API_KEY | Skips skill stage entirely, pipeline continues |
| Script subprocess timeout (>60s) | SkillExecutor catches, logs warning, returns empty result |
| Script stdout is invalid JSON | Caught, logged, empty result returned |
| Script raises exception | stderr captured in result, pipeline continues |
| LLM composer fails | Returns None, pipeline continues without skill augmentation |

---

## 7. Data Flow & Pydantic Schemas

### 7.1 Schema Hierarchy

```
ECAOutput
├── readme: str
├── file_tree: Dict[str, Any]
├── classified_files: ClassifiedFiles
│   ├── frontend: List[str]
│   ├── backend: List[str]
│   ├── config: List[str]
│   ├── docs: List[str]
│   └── unknown: List[str]
└── chunks: List[FileChunk]
    ├── file: str
    └── content: str

RepoEvidence (assembled by evidence_manifest.py)
├── has_http_api: bool          ← actual endpoints found
├── has_grpc: bool              ← .proto files or grpc deps
├── actual_endpoints: List[Dict]
├── grpc_rpcs: List[Dict]
├── has_database: bool          ← DB deps detected
├── has_auth: bool              ← auth deps or auth/ dirs
├── has_docker: bool            ← Dockerfile present
├── has_kubernetes: bool        ← k8s/ dir or kind: Deployment YAML
├── has_android: bool           ← AndroidManifest.xml present
├── has_ios: bool               ← .xcodeproj / Podfile present
├── has_desktop: bool           ← .pbl/.sln/.csproj or electron dep
├── has_gdpr_mention: bool      ← README/docs mention GDPR/PII
├── has_tests: bool             ← test/ dirs or *_test.py files
├── platform: str               ← "android"|"ios"|"desktop"|"web"|"server"|"library"|"unknown"
├── dep_categories: DepCategories
│   ├── database: List[str]
│   ├── auth: List[str]
│   ├── grpc: List[str]
│   ├── infra: List[str]
│   ├── framework: List[str]
│   └── other: List[str]
├── build_tool: str             ← "gradle"|"maven"|"npm"|"pip"|"unknown"
└── primary_language: str

ExtractedFeature
├── id: str                     ← "feat-NNN" (1-indexed, zero-padded)
├── name: str                   ← Title Case, product-facing
├── description: str            ← 1-2 sentences grounded in evidence
├── source_modules: List[str]   ← file names proving feature exists
└── confidence: float           ← 0.5–1.0 (calibrated post-extraction)

ValidatedFeature
├── id: str                     ← re-indexed after dedup/merge
├── name: str                   ← snake_case canonical identifier
├── description: str            ← from highest-confidence source
├── confidence: float           ← max-pooled, never inflated
└── merge_of: List[str]         ← original input ids collapsed here

ProductProfile
├── name: str                   ← snake_case archetype label
├── summary: str                ← ≤120 words, template-driven
└── core_capabilities: List[str] ← Title Case, one per high-conf feature

BusinessContext
├── product_type: str           ← e.g. "API Backend Service"
├── primary_users: List[str]    ← e.g. ["Authenticated Users", "Developers"]
└── core_value: str             ← derived from top 3 features

FunctionalRequirement
├── id: str                     ← "FR-N" (1-indexed)
├── description: str            ← SHALL-style, specific and testable
├── linked_feature: str         ← snake_case source ValidatedFeature name
└── acceptance_criteria: List[str]

NonFunctionalRequirement
├── id: str                     ← "NFR-N" (1-indexed)
├── category: Literal["performance","security","scalability","availability"]
└── description: str            ← SHALL-style with measurable condition

BRDValidationResult
├── score: float                ← 0.0–1.0 (9-dimension average)
├── issues: List[str]           ← specific, actionable violation messages
└── needs_revision: bool        ← True if score < 0.85

ExtractedEntity
├── name: str                   ← entity/class name
├── source_file: str            ← file where found
├── table_name: Optional[str]   ← DB table name if JPA
├── fields: List[str]           ← field/property names
└── entity_type: Literal["jpa_entity","data_class","proto_message","generic_model"]

SkillActivation
├── skill_id: str               ← directory name of the pack
├── skill_name: str             ← display_name from SKILL.md
├── score: float                ← 0.0–1.0 max-of-dimensions score
├── auto_generated: bool        ← True if from SkillComposer
└── scripts_run: List[str]      ← script subcommands executed

SkillExecutionResult
├── activated_skills: List[SkillActivation]
├── additional_features: List[Dict]  ← [{name, description, confidence}]
├── additional_signals: Dict[str, Any]
└── brd_section_hints: Dict[str, str]

MinimalBRD (from payload_converter.py — deterministic, no LLM)
├── repo_name: str
├── summary: str
├── validation_score: float
├── validation_passed: bool
├── features: List[AnalysisFeature]
├── requirements: List[Requirement]
├── gaps: List[str]
└── modules_detected: List[str]
```

### 7.2 Inter-Stage Data Contract

```
RepoScanner ──► {files[]} ──► FileClassifier ──► {classified_files[]}
                                                         │
                                                         ▼
                                               ContentProcessor
                                                         │
                                                         ▼
                                                   {chunks[]}
                                                    │       │
                                                    │       ▼
                                                    │  RepoContextBuilder ──► RepoContext
                                                    │       │
                                                    │       ▼
                                                    │  APIExtractor + DependencyExtractor + EntityExtractor
                                                    │       │
                                                    │       ▼
                                                    │  EvidenceManifest ──► RepoEvidence
                                                    │
                                                    ▼
                                             ContextAggregator
                                                    │
                                                    ▼
                                             ContextNormalizer ──► {normalized_modules[]}
                                                    │
                                                    ▼
                                             ContextValidator ──► {score, valid}
                                                    │
                                                    ▼
                                          FinalOutputBuilder ──► canonical payload
                                                    │
                                    ┌───────────────┘
                                    │
                                    ▼
                         SkillPackMatcher ──► List[SkillActivation]
                                    │
                                    ▼
                         SkillPackExecutor ──► SkillExecutionResult
                                    │
                                    ▼
                         FeatureExtractionAgent ──► {features[]}
                         (skill features merged in, signals in LLM prompt)
                                    │
                                    ▼
                           FeatureValidator ──► {validated_features[]}
                                    │
                         ┌──────────┴──────────┐
                         │                     │
                         ▼                     ▼
              ProductUnderstanding    FunctionalRequirements
                         │                     │
                         ▼                     ▼
              BusinessUnderstanding   NonFunctionalRequirements
                         │
                         ▼
                    BRDComposer ──► initial_markdown
                         │
                         ▼
                    BRDValidator ──► {score, issues[]}
                         │
                    (if score < 0.85)
                         ▼
                    BRDFixLoop ──► final_markdown
                         │
                         ▼
                  DocumentGenerator ──► .docx
```

---

## 8. LLM Integration Points

All LLM calls route through `app/utils/llm_client.py`. The pipeline **never blocks** on LLM availability — every call has a deterministic fallback.

### 8.1 LLM Client Configuration

| Setting | Env Var | Default | Notes |
|---------|---------|---------|-------|
| API Key | `OPENAI_API_KEY` | — | Required for LLM phases |
| Model | `OPENAI_MODEL` | `gpt-4o-mini` | Supports o1/o3/o4/gpt-5 families |
| Max Tokens | `OPENAI_MAX_TOKENS` | `2048` | Per-call limit |
| Temperature | — | `0` | Always 0, not configurable |
| Retries | — | `3` | Exponential backoff (2s, 4s, 6s) |
| JSON Min Tokens | `OPENAI_JSON_MIN_TOKENS` | `4096` | For o-series/GPT-5 models |
| Token Multiplier | `OPENAI_JSON_TOKEN_MULTIPLIER` | `3` | Headroom for JSON calls |
| Reasoning Effort | `OPENAI_REASONING_EFFORT` | `minimal` | GPT-5 only |
| Verbosity | `OPENAI_VERBOSITY` | `low` | GPT-5 only |

**Model family detection:**
- Models starting with `o1`, `o3`, `o4` or containing `gpt-5` use `max_completion_tokens` instead of `max_tokens`
- These models do not accept the `temperature` parameter
- GPT-5 models additionally accept `reasoning_effort` and `verbosity`

### 8.2 LLM Call Map

```
Phase 2 — Feature Extraction
  FeatureExtractionAgent.extract_features()
    └── llm_json_call(DYNAMIC_EXTRACTION_PROMPT, repo_context_str)
        Fallback: _fallback_extraction() — module names as features

Phase 2.5 — Hallucination Pruning  (optional)
  llm_enrichment.prune_hallucinated_features()
    └── llm_json_call(PRUNE_SYSTEM_PROMPT, features + readme)
        Fallback: return original features unchanged

Phase 3 — Product Archetype Detection
  ProductUnderstandingAgent._llm_detect_archetype()
    └── llm_json_call(_ARCHETYPE_SYSTEM_PROMPT, evidence + readme + features)
        Fallback: _detect_archetype() keyword voting via archetype_registry.json

Phase 3 — Functional Requirement Generation
  FunctionalRequirementGenerator._generate_llm_requirements()
    └── llm_json_call(_FR_GEN_SYSTEM_PROMPT, feature + evidence)
        Fallback: _generate_deterministic_requirements()

Phase 3.5 — Feature Description Enrichment  (optional)
  llm_enrichment.enrich_features()
    └── llm_json_call(FEATURE_SYSTEM_PROMPT, feature + evidence) × N features
        Fallback: original description preserved

Phase 3.5 — Core Value Statement  (optional)
  llm_enrichment.enrich_core_value()
    └── llm_json_call(CORE_VALUE_SYSTEM_PROMPT, top 5 features)
        Fallback: concatenated feature names

Phase 3.5 — Enterprise Artifacts  (optional)
  llm_enrichment.enrich_enterprise_artifacts()
    └── llm_json_call(ENTERPRISE_ARTIFACTS_PROMPT, system_type + tech_stack + features + evidence)
        Fallback: {} (BRDComposer uses deterministic section templates)

Phase 3.7 — BRD Deep Enrichment  (optional, 7 calls)
  brd_enrichment_agent.enrich_brd_context()
    ├── enrich_executive_summary()   → llm_json_call(_EXEC_SYS, ...)
    ├── enrich_business_context()    → llm_json_call(_BIZ_SYS, ...)
    ├── enrich_stakeholders()        → llm_json_call(_STAKE_SYS, ...)
    ├── enrich_functional_requirements() → batched llm_json_call(_FR_SYS, ...) × ceil(N/8)
    ├── enrich_nfrs()                → llm_json_call(_NFR_SYS, ...)
    ├── enrich_roadmap()             → llm_json_call(_ROADMAP_SYS, ...)
    └── enrich_open_issues()         → llm_json_call(_ISSUES_SYS, ...)
        All fallback: {} (BRDComposer uses deterministic section templates)

Phase 1.5 — Skill Composer  (optional, fires only when no pack matches)
  SkillComposer.compose_missing_skill()
    └── llm_text_call(COMPOSE_SYSTEM_PROMPT, repo_context + evidence)
        Output: SKILL.md content (Markdown)
        Fallback: None — skill stage skipped, pipeline continues
```

### 8.3 Anti-Hallucination Guarantees

1. **Full context injection** — every prompt receives the complete structured JSON input; the model has no reason to guess
2. **temperature=0** — deterministic output across identical inputs
3. **Evidence-grounded BRD** — `RepoEvidenceManifest` flags prevent phantom tech claims (Kubernetes, Docker, GDPR, etc.) from appearing in the BRD unless the repo actually contains evidence
4. **Semantic pruning** — `prune_hallucinated_features()` cross-checks extracted features against the README as ground truth
5. **BRD Validator dimension 3** — "No-Hallucination" checks that no FR-IDs appear in the BRD that weren't in the input set
6. **BRD Validator dimension 9** — "Tech Grounding" checks that tech claims in the BRD are backed by `RepoEvidenceManifest`

---

## 9. API Endpoints

The FastAPI server is started with:
```bash
uvicorn app.api.main:app --reload
# UI:     http://localhost:8000
# Docs:   http://localhost:8000/docs
# Health: http://localhost:8000/health
```

### 9.1 Core Pipeline Endpoints

| Method | Path | Input | Output | Notes |
|--------|------|-------|--------|-------|
| `GET` | `/` | — | Frontend UI or welcome JSON | Serves `static/index.html` |
| `GET` | `/health` | — | `{status, service}` | Health check |
| `POST` | `/analyze` | `{repo_url, output_path?}` | `{status, data: final_payload}` | Phase 1 only |
| `POST` | `/analyze-and-convert` | `{repo_url, output_path?}` | `{status, pipeline, brd, markdown, validation}` | Full end-to-end |
| `POST` | `/convert` | `{payload: Dict}` | `{status, brd: MinimalBRD}` | Pre-computed payload → MinimalBRD |

### 9.2 Granular Agent Endpoints

| Method | Path | Input | Output |
|--------|------|-------|--------|
| `POST` | `/extract-features` | `{normalized_modules[], chunks[]}` | `{status, data: FeatureExtractionResult}` |
| `POST` | `/validate-features` | `{features[]}` | `{status, data: FeatureValidationResult}` |
| `POST` | `/understand-product` | `{validated_features[]}` | `{status, data: ProductUnderstandingResult}` |
| `POST` | `/generate-requirements` | `{validated_features[]}` | `{status, data: FunctionalRequirementsResult}` |
| `POST` | `/generate-nfrs` | `{validated_features[], product_name?}` | `{status, data: NonFunctionalRequirementsResult}` |
| `POST` | `/compose-brd` | `{product_data, features_data, fr_data, nfr_data}` | `{status, data: markdown_string}` |
| `POST` | `/validate-brd` | `{brd_markdown}` | `{status, data: BRDValidationResult}` |
| `POST` | `/fix-brd` | `{initial_brd_markdown}` | `{status, data: {final_markdown, final_validation, iterations}}` |

### 9.3 Skill Pack Endpoints

| Method | Path | Input | Output |
|--------|------|-------|--------|
| `GET` | `/skills` | — | `{skill_packs[], total, curated, generated}` |
| `GET` | `/skills/{id}` | — | Full skill pack metadata + instructions |
| `POST` | `/skills/compose` | `{evidence, repo_context, detected_deps?}` | `{status, skill_id, name, ...}` |
| `PUT` | `/skills/{id}/promote` | — | `{status, from, to}` — move generated → curated |

### 9.4 Download Endpoints

| Method | Path | Input | Output |
|--------|------|-------|--------|
| `POST` | `/download/brd-markdown` | `{brd_markdown, filename?}` | `.md` file stream |
| `POST` | `/download/brd-docx` | `{brd_markdown, filename?}` | `.docx` file stream |
| `POST` | `/download/pipeline-json` | `{...payload}` | `.json` file stream |

---

## 10. Configuration Reference

### 10.1 Environment Variables (`.env`)

```env
# Required for LLM phases. Without this, pipeline runs in deterministic-only mode.
OPENAI_API_KEY=sk-your-key-here

# Optional — model selection
OPENAI_MODEL=gpt-4o-mini          # Default: gpt-4o-mini
OPENAI_MAX_TOKENS=2048            # Default: 2048

# Optional — o-series / GPT-5 model tuning
OPENAI_JSON_MIN_TOKENS=4096       # Minimum completion tokens for JSON calls
OPENAI_JSON_TOKEN_MULTIPLIER=3    # Headroom multiplier for JSON calls
OPENAI_REASONING_EFFORT=minimal   # GPT-5 reasoning effort
OPENAI_VERBOSITY=low              # GPT-5 verbosity
```

### 10.2 Language Registry (`app/eca/config/language_registry.json`)

Single source of truth for all language knowledge. **Zero Python changes required** to add a new language.

```json
{
  "ignore_dirs": ["node_modules", ".git", "dist", ...],
  "universal_binary_extensions": [".exe", ".dll", ".png", ...],
  "universal_config_extensions": [".yaml", ".yml", ".toml", ...],
  "universal_doc_extensions": [".md", ".txt", ".rst", ...],
  "languages": {
    "python": {
      "extensions": [".py", ".pyw", ".pyi"],
      "role": "backend",
      "entry_points": ["main.py", "app.py", "manage.py", ...],
      "build_files": ["requirements.txt", "pyproject.toml", ...],
      "binary": false,
      "notes": "CPython, PyPy"
    }
  }
}
```

**Registered languages (40+):** Python, JavaScript, TypeScript, JSX, TSX, Vue, Svelte, HTML, CSS, Java, Kotlin, C#, VB.NET, VB6, F#, Go, Rust, C++, C, Swift, Objective-C, Ruby, PHP, Scala, Dart, Elixir, Erlang, Haskell, COBOL, PowerBuilder, ABAP, Fortran, Pascal, Lua, R, Julia, MATLAB, SQL, Shell, PowerShell, Perl, Groovy, Clojure, Terraform, Dockerfile, GraphQL, Proto, Jupyter, Assembly

### 10.3 Archetype Registry (`app/analysis/config/archetype_registry.json`)

Drives `ProductUnderstandingAgent` keyword voting fallback. **Zero Python changes required** to add a new archetype.

```json
{
  "archetypes": {
    "api_backend_service": {
      "keywords": ["rest_api", "routing", "grpc", "endpoint", "controller"],
      "display": "API Backend Service",
      "fragment": "backend API service exposing structured endpoints"
    }
  }
}
```

**Registered archetypes (13):** social_platform, api_backend_service, data_platform, auth_service, e_commerce, devops_toolchain, desktop_ui_app, ml_ai_platform, mobile_app, iot_edge, reporting_analytics, cms_content, erp_enterprise

---

## 11. Error Handling Patterns

### 11.1 LLM Failure Handling

```
LLM call attempted
    │
    ├── RateLimitError ──► retry up to 3× with exponential backoff (2s, 4s, 6s)
    ├── APIConnectionError ──► same retry logic
    ├── APIError (non-transient) ──► raise RuntimeError immediately
    ├── Empty response ──► raise RuntimeError with finish_reason + token usage
    ├── Invalid JSON ──► raise ValueError with raw response preview
    └── Any exception in enrichment ──► _safe_call() returns {}, pipeline continues
```

### 11.2 Pipeline Failure Handling

| Scenario | Behavior |
|----------|----------|
| No `OPENAI_API_KEY` | All LLM phases silently skipped. Deterministic output used throughout. |
| LLM feature extraction fails | `_fallback_extraction()` — module names become generic features |
| LLM archetype detection fails | `_detect_archetype()` keyword voting via `archetype_registry.json` |
| LLM FR generation fails | `_generate_deterministic_requirements()` generic SHALL-style FRs |
| Any `brd_enrichment_agent` call fails | `_safe_call()` returns `{}`, BRDComposer uses deterministic section templates |
| BRD score < 0.85 | `BRDFixLoop` applies up to 2 deterministic repair passes |
| RepoScanner clone failure | Returns `{"error": "..."}`, `run_end_to_end()` raises `RuntimeError` |
| Missing README | `RepoContextBuilder` waterfall falls through to `[NO_DOCUMENTATION]` signal |
| Binary / unreadable file | `is_binary()` check in scanner; `UnicodeDecodeError` silently skipped in `ContentProcessor` |
| Unknown file extension | `language_loader.py` returns `"unknown"` role; file still processed as plain text |
| API endpoint exception | `try/except` in all route handlers → `HTTPException(500, detail=str(e))` + `traceback.print_exc()` |
| No skill pack matches + no LLM key | Skill stage entirely skipped, pipeline continues without augmentation |
| Skill script subprocess timeout | Caught by executor; empty result returned; pack contributes nothing |
| Skill script invalid JSON output | Caught; error captured in `SkillExecutionResult`; pipeline continues |

### 11.3 BRD Validation — 9 Dimensions

| # | Dimension | What is Checked | Scoring |
|---|-----------|----------------|---------|
| 1 | **Completeness** | All 16 required section headings present | `found / 16` |
| 2 | **Traceability** | Every input feature name and FR-ID appears in BRD | `found / total` |
| 3 | **No-Hallucination** | BRD contains no FR-IDs absent from input set | `1 - (phantom / brd_fr_ids)` |
| 4 | **Clarity** | No banned vague phrases (seamlessly, world-class, etc.) | `1 - violations × 0.1` |
| 5 | **FR Testability** | FR lines contain testable verbs (SHALL, MUST, validates, etc.) | `testable / fr_lines` |
| 6 | **NFR Specificity** | NFR SLA targets have real values, not TBD/Strict/N/A | `1 - placeholders / nfr_lines` |
| 7 | **Stakeholder Specificity** | Roles are project-specific, not generic End User/Admin | Binary: 1.0 or 0.6 |
| 8 | **Section Depth** | Every section ≥30 words; Executive Summary ≥60 words | `adequate / checked` |
| 9 | **Tech Grounding** | BRD tech claims backed by `RepoEvidenceManifest` | `1 - failed / total_checks` |

**Aggregate score** = equal-weight average of all 9 dimensions  
**Revision threshold** = 0.85 (score < 0.85 → `needs_revision = True`)

---

## 12. Design Principles

| # | Principle | Implementation |
|---|-----------|---------------|
| 1 | **Reliability First** | Deterministic pipeline always produces a valid BRD. LLM is optional enrichment only. Every LLM call has a working fallback. |
| 2 | **Data-First** | Pydantic schemas defined before code. All inter-stage outputs are validated. `app/schemas/models.py` is the single contract. |
| 3 | **No Hallucination** | Full structured context injected into every prompt. `temperature=0`. Semantic pruning removes false positives. `RepoEvidenceManifest` prevents phantom tech claims. |
| 4 | **Absolute Traceability** | Every feature maps to `source_modules[]` evidence. Every FR maps to a `linked_feature`. BRDValidator enforces this across 9 scoring dimensions. |
| 5 | **Repository Isolation** | Each run clones into `<repo_name>/repo/src/`. Successive runs never cross-contaminate. |
| 6 | **Self-Annealing** | BRD score < 0.85 → `BRDFixLoop` applies deterministic patches → re-validates. Max 2 iterations. |
| 7 | **Zero Hardcoded Language Facts** | All 40+ languages live in `language_registry.json`. All 13 archetypes live in `archetype_registry.json`. Adding support requires only a JSON entry. |
| 8 | **Evidence-Grounded Output** | `RepoEvidenceManifest` is assembled from actual file system inspection (not keyword guessing). BRD sections check evidence flags before writing platform/infra/compliance content. |
| 9 | **Dual-Audience Writing** | `brd_enrichment_agent.py` prompts enforce plain English for business stakeholders + technical notes for engineers in every enriched section. |
| 10 | **Batched LLM Calls** | FR enrichment processes 8 FRs per call to avoid token-limit failures on large repositories. |
| 11 | **Zero Hardcoded Domain Logic** | All skill pack detection signals live in SKILL.md YAML frontmatter. Adding or removing domains never requires Python changes. |
| 12 | **Self-Growing Intelligence** | SkillComposer auto-generates new skill packs for novel repository types. Generated packs are idempotent (fingerprinted) and promotable to stable packs. |

---

## 13. Directory Structure

```
Analyst-Agent/
├── app/
│   ├── api/
│   │   └── main.py                         # FastAPI entry point — ~20 routes
│   ├── pipeline/
│   │   └── runner.py                       # Master orchestrator (run_full_pipeline_service + run_end_to_end + run_pipeline)
│   │
│   ├── eca/                                # Stage 1: Extract, Classify, Aggregate
│   │   ├── repo_scanner.py                 # git clone + os.walk file scan
│   │   ├── file_classifier.py             # Path heuristics + registry role lookup
│   │   ├── content_processor.py            # Chunked file content reader (~3200 chars/chunk)
│   │   ├── language_loader.py              # LRU-cached pure reader over language_registry.json
│   │   ├── extractor.py                    # Standalone ECA orchestrator (builds ECAOutput)
│   │   ├── api_extractor.py                # Spring MVC annotations + .proto gRPC RPC parser
│   │   ├── entity_extractor.py             # @Entity JPA, Kotlin data class, proto message
│   │   ├── dependency_extractor.py         # Gradle/Maven/npm/pip build file parser
│   │   ├── defect_extractor.py             # TODO/FIXME/HACK/jcenter/hardcoded creds scanner
│   │   ├── repo_context_builder.py         # Priority waterfall → RepoContext dict
│   │   ├── evidence_manifest.py            # RepoEvidenceManifest from file system + extractors
│   │   └── config/
│   │       └── language_registry.json      # ★ Single source of truth for all language knowledge
│   │
│   ├── context/                            # Stage 2: Context Intelligence
│   │   ├── aggregator.py                   # Chunks → modules by top-level directory
│   │   ├── normalizer.py                   # snake_case, dedup, noise removal, UUID5 IDs
│   │   └── validator.py                    # Completeness scoring, core structure check
│   │
│   ├── analysis/                           # Stages 3–4: Analysis & Composition
│   │   ├── feature_extraction_agent.py     # LLM-primary feature extraction + confidence calibration
│   │   ├── feature_validator.py            # 3-pass: dedup → merge groups → normalise
│   │   ├── feature_interpretation_agent.py # Maps raw signals to evidence (standalone)
│   │   ├── business_understanding_agent.py # Keyword voting → product_type, primary_users, core_value
│   │   ├── product_understanding_agent.py  # LLM archetype detection + keyword voting fallback
│   │   ├── archetype_loader.py             # LRU-cached reader over archetype_registry.json
│   │   ├── functional_requirement_generator.py  # Template → LLM → deterministic FR generation
│   │   ├── non_functional_requirement_generator.py  # Keyword-triggered NFR templates (max 8)
│   │   ├── payload_converter.py            # Canonical payload → MinimalBRD (deterministic)
│   │   ├── brd_composer.py                 # 16-section Markdown assembly (evidence-aware)
│   │   ├── brd_enrichment_agent.py         # 7 LLM calls for deep BRD section enrichment
│   │   ├── brd_validator.py                # 9-dimension BRD quality scorer (threshold 0.85)
│   │   ├── brd_fix_loop.py                 # Self-annealing repair loop (max 2 passes)
│   │   ├── fix_loop.py                     # Low-level fix helpers
│   │   ├── document_generator.py           # Markdown → .docx via python-docx
│   │   └── config/
│   │       └── archetype_registry.json     # ★ Single source of truth for product archetypes
│   │
│   ├── skills/                             # ★ Dynamic Skill Pack Engine
│   │   ├── __init__.py
│   │   ├── skill_loader.py                 # SKILL.md YAML frontmatter parser (no PyYAML dep)
│   │   ├── skill_matcher.py                # Max-of-dimensions scoring against RepoEvidenceManifest
│   │   ├── skill_executor.py               # Subprocess runner per activated pack
│   │   ├── skill_composer.py               # LLM auto-generation of novel skill packs
│   │   └── packs/
│   │       ├── web_api/                    # REST/gRPC API analysis
│   │       ├── ml_pipeline/                # ML model & training pipeline analysis
│   │       ├── data_platform/              # Data pipeline & warehouse analysis
│   │       ├── mobile_app/                 # Android/iOS screen & permission analysis
│   │       ├── cli_tool/                   # CLI framework instructions (no scripts)
│   │       └── _generated/                 # Auto-generated packs (gitignored contents)
│   │
│   ├── utils/
│   │   ├── llm_client.py                   # OpenAI wrapper (retry, JSON mode, temperature=0, o-series/GPT-5)
│   │   └── llm_enrichment.py              # 5 enrichment functions + hallucination pruning
│   │
│   ├── output/
│   │   └── final_output_builder.py         # Merges Phase 1 outputs into canonical payload
│   │
│   ├── schemas/
│   │   └── models.py                       # ★ All Pydantic models and data contracts
│   │
│   ├── validation/                         # Validation utilities
│   └── tests/                              # pytest test suite
│       ├── test_brd_grounding.py
│       ├── test_entity_extractor.py
│       ├── test_llm_client.py
│       └── test_pipeline.py
│
├── architecture/
│   ├── pipeline_sop.md                     # Pipeline Standard Operating Procedure
│   ├── technical_overview.md               # Technical architecture overview
│   └── BRD.md                              # Sample generated BRD for reference
│
├── runtime/
│   └── pipeline_out/                       # All generated BRD artifacts (.md, .docx)
│       └── <repo_name>/                    # Isolated per-repo directory
│           ├── brd/                        # Final BRD output
│           ├── debug/                      # Intermediate JSON dumps
│           └── repo/src/                   # Cloned source code
│
├── static/
│   └── index.html                          # Frontend UI (Tailwind CSS dark-mode)
│
├── .env.example                            # Environment variable template
├── .env                                    # Local secrets (gitignored)
├── .gitignore
├── .graphifyignore
├── requirements.txt                        # Python dependencies
├── Agents.md                               # Multi-agent collaboration guide
├── Architecture.md                         # ← This file
└── README.md                               # Setup and usage guide
```

---

## Quick Reference

### Adding a New Language
Edit `app/eca/config/language_registry.json`. No Python changes required.

### Adding a New Product Archetype
Edit `app/analysis/config/archetype_registry.json`. No Python changes required.

### Adding a New Skill Pack
1. Create `app/skills/packs/<domain>/SKILL.md` with YAML frontmatter
2. Optionally add `scripts/extractor.py` (stdlib only, argparse CLI, JSON to stdout)
3. No registration required — `skill_loader.py` auto-discovers on startup

Or let `SkillComposer` auto-generate one on first encounter of a novel repo type.

### Starting Points (by task)

| Task | File to Modify |
|------|---------------|
| Add new language support | `app/eca/config/language_registry.json` |
| Add new product archetype | `app/analysis/config/archetype_registry.json` |
| Add new skill pack | `app/skills/packs/<domain>/SKILL.md` |
| Modify skill scoring | `app/skills/skill_matcher.py` |
| Modify skill execution | `app/skills/skill_executor.py` |
| Add new analysis agent | `app/analysis/<agent_name>.py` |
| Add new file extractor | `app/eca/<extractor_name>.py` |
| Modify BRD structure | `app/analysis/brd_composer.py` |
| Modify validation rules | `app/analysis/brd_validator.py` |
| Add new API endpoint | `app/api/main.py` |
| Add/modify Pydantic schemas | `app/schemas/models.py` |

### Running Tests
```bash
pytest app/tests/ -v
```

### Running Individual Tools (CLI)
```bash
python -m app.pipeline.runner <repo_url> --outdir runtime/pipeline_out
python -m app.eca.repo_scanner <repo_url>
python -m app.eca.language_loader                          # self-test
python -m app.analysis.archetype_loader                    # self-test
python -m app.output.final_output_builder --scan ... --classified ... --chunks ... --modules ... --validation ...
```

---

*Last updated: 2026-05-28*
