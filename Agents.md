# Agents.md — Multi-Agent Collaboration Guide

This document explains how multiple agents can collaborate on developing and extending the **Analyst Agent** project. It provides an overview of the system architecture, key interfaces, development patterns, and guidelines for agents working on this codebase.

---

## Project Overview

**Analyst Agent** is an enterprise-grade backend system that converts any GitHub repository into a comprehensive Business Requirement Document (BRD). The pipeline follows a **deterministic-first** approach — all structural analysis is performed by rule-based agents, with OpenAI used selectively in optional enrichment and hallucination-pruning steps.

**Core Capabilities:**
- Clone and analyze any public GitHub repository
- Classify files by language and role (40+ languages supported)
- Extract features, entities, dependencies, and API routes
- Dynamically activate domain-specific skill packs for specialized analysis
- Generate functional and non-functional requirements
- Compose a validated 16-section BRD document
- Export to Markdown or Word (.docx)

---

## System Architecture

### Pipeline Flow (with Skill Pack Integration)

```
GitHub Repo URL
    → [1] RepoScanner         — clone & file tree
    → [2] FileClassifier      — categorize source files (driven by language_registry.json)
    → [3] ContentProcessor    — chunk & extract content
    → [3.1] Sub-Extractors    — API, Entity, Dependency, Defect signal extraction
    → [3.5] RepoContextBuilder — priority waterfall intent signals
    → [3.6] EvidenceManifest  — structured repo evidence
    → [4] ContextAggregator & Normalizer
    → [4.5] SkillPackMatcher  — dynamic skill pack detection
    → [4.7] SkillPackExecutor — run activated skill scripts
    → [5] FeatureExtractionAgent (LLM-primary + skill features merged)
    → [6] FeatureValidator
    → [6.5] Semantic Feature Pruning (LLM, optional)
    → [7] ProductUnderstandingAgent
    → [8] FunctionalRequirementGenerator
    → [9] NonFunctionalRequirementGenerator
    → [3.5L] LLM Enrichment (optional)
    → [3.6L] BusinessUnderstandingAgent
    → [3.7] BRD Deep Enrichment (7 LLM calls, optional)
    → [10] BRDComposer → BRDValidator → BRDFixLoop → BRD (.md / .docx)
```

### 3-Layer Architecture (A.N.T.)

| Layer | Location | Purpose |
|-------|----------|---------|
| **Architecture** | `architecture/` | Technical SOPs in Markdown. Updated before code changes. |
| **Navigation** | `app/pipeline/` | Orchestration layer. Routes data between tools. No complex logic performed directly. |
| **Tools** | `app/` | Deterministic Python scripts. Atomic, Pydantic-validated, and independently testable. |

### Pipeline State Machine

```
CREATED → INGESTING → ECA_DONE → CONTEXT_READY → NORMALIZED → VALIDATED
        → SKILLS_ACTIVATED → ANALYZED → [LLM_ENRICHED] → BRD_READY
        → VALIDATING → IMPROVING → COMPLETED / FAILED
```

---

## Directory Structure

```text
Analyst-Agent/
├── app/
│   ├── api/
│   │   └── main.py                         # FastAPI entry point — ~20 routes
│   ├── pipeline/
│   │   └── runner.py                       # Master orchestrator (run_full_pipeline_service + run_end_to_end + run_pipeline)
│   ├── eca/                                # Stage 1: Extract, Classify, Aggregate
│   │   ├── repo_scanner.py                 # git clone + os.walk file scan
│   │   ├── file_classifier.py             # Path heuristics + language_registry.json role lookup
│   │   ├── content_processor.py            # Chunked file content reader (~3200 chars/chunk)
│   │   ├── language_loader.py              # LRU-cached pure reader over language_registry.json
│   │   ├── extractor.py                    # Standalone ECA orchestrator (builds ECAOutput)
│   │   ├── api_extractor.py                # Spring MVC annotations + .proto gRPC RPC parser
│   │   ├── entity_extractor.py             # @Entity JPA, Kotlin data class, proto message parser
│   │   ├── dependency_extractor.py         # Gradle/Maven/npm/pip build file parser
│   │   ├── defect_extractor.py             # TODO/FIXME/HACK/hardcoded creds scanner
│   │   ├── repo_context_builder.py         # Priority waterfall → RepoContext dict
│   │   ├── evidence_manifest.py            # RepoEvidenceManifest from file system + extractors
│   │   └── config/
│   │       └── language_registry.json      # ★ Single source of truth for all language knowledge
│   ├── context/                            # Stage 2: Context Intelligence
│   │   ├── aggregator.py                   # Chunks → modules by top-level directory
│   │   ├── normalizer.py                   # snake_case, dedup, noise removal, UUID5 IDs
│   │   └── validator.py                    # Completeness scoring, core structure check
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
│   │   ├── brd_enrichment_agent.py         # 7 LLM calls for deep BRD section enrichment (Phase 3.7)
│   │   ├── brd_validator.py                # 9-dimension BRD quality scorer (threshold 0.85)
│   │   ├── brd_fix_loop.py                 # Self-annealing repair loop (max 2 passes)
│   │   ├── fix_loop.py                     # Low-level fix helpers
│   │   ├── document_generator.py           # Markdown → .docx via python-docx
│   │   └── config/
│   │       └── archetype_registry.json     # ★ Single source of truth for product archetypes
│   ├── skills/                             # ★ Dynamic Skill Pack Engine
│   │   ├── skill_loader.py                 # SKILL.md YAML frontmatter parser
│   │   ├── skill_matcher.py                # Max-of-dimensions scoring against RepoEvidenceManifest
│   │   ├── skill_executor.py               # Subprocess runner per activated pack
│   │   ├── skill_composer.py               # LLM auto-generation of novel skill packs
│   │   └── packs/
│   │       ├── web_api/                    # REST/gRPC API analysis
│   │       ├── ml_pipeline/                # ML model & training pipeline analysis
│   │       ├── data_platform/              # Data pipeline & warehouse analysis
│   │       ├── mobile_app/                 # Android/iOS screen & permission analysis
│   │       ├── cli_tool/                   # CLI framework instructions (no scripts)
│   │       └── _generated/                 # Auto-generated packs (reusable)
│   ├── utils/
│   │   ├── llm_client.py                   # OpenAI wrapper (retry, JSON mode, temperature=0, o-series/GPT-5 support)
│   │   └── llm_enrichment.py              # 5 enrichment functions + hallucination pruning
│   ├── output/
│   │   └── final_output_builder.py         # Merges Phase 1 outputs into canonical payload
│   ├── schemas/
│   │   └── models.py                       # ★ All Pydantic models and data contracts
│   ├── validation/                         # Validation utilities
│   └── tests/                              # pytest test suite
│       ├── test_brd_grounding.py
│       ├── test_entity_extractor.py
│       ├── test_llm_client.py
│       └── test_pipeline.py
├── architecture/
│   ├── pipeline_sop.md                     # Pipeline Standard Operating Procedure
│   ├── technical_overview.md               # Technical architecture overview
│   └── BRD.md                              # Sample generated BRD for reference
├── runtime/
│   └── pipeline_out/                       # All generated BRD artifacts (.md, .docx)
│       └── <repo_name>/                    # Isolated per-repo directory
│           ├── brd/                        # Final BRD output
│           ├── debug/                      # Intermediate JSON dumps
│           └── repo/src/                   # Cloned source code
├── static/
│   └── index.html                          # Frontend UI (Tailwind CSS dark-mode)
├── .env.example                            # Environment variable template
├── requirements.txt
├── Agents.md                               # This file (Multi-agent collaboration guide)
├── Architecture.md                         # Full technical architecture document
└── README.md                               # Setup and usage guide
```

---

## Key Interfaces & Data Contracts

All inter-module communication uses Pydantic models defined in [app/schemas/models.py](app/schemas/models.py).

### Core Input/Output Schemas

| Module | Input | Output |
|--------|-------|--------|
| **RepoScanner** | `repo_url`, `dest_dir`, `skip_clone` | `{repo_name, files, readme, file_tree}` |
| **FileClassifier** | `scan_data` | `{classified_files: [{path, category, confidence}]}` |
| **ContentProcessor** | `classified_data`, `dest_repo_dir` | `{chunks: [{chunk_id, file_path, category, content}]}` |
| **RepoContextBuilder** | `repo_root`, `chunks_data`, `dep_data`, `evidence` | `RepoContext` dict |
| **EvidenceManifest** | `repo_dir`, `api_data`, `dep_data` | `RepoEvidence` dict |
| **FeatureExtractionAgent** | `normalized_modules`, `chunks_list`, `repo_context`, `skill_results` | `{features: [ExtractedFeature]}` |
| **FeatureValidator** | `raw_features` | `{validated_features: [ValidatedFeature]}` |
| **ProductUnderstandingAgent** | `validated_features`, `repo_context`, `evidence` | `{product: {name, summary, core_capabilities}}` |
| **BusinessUnderstandingAgent** | `validated_features`, `system_type` | `{business_context: {product_type, primary_users, core_value}}` |
| **FunctionalRequirementGenerator** | `validated_features` | `{functional_requirements: [FunctionalRequirement]}` |
| **NonFunctionalRequirementGenerator** | `system_type`, `tech_stack` | `{non_functional_requirements: [NonFunctionalRequirement]}` |
| **BRDComposer** | `business_context`, `features`, `frs`, `nfrs`, `evidence` | `markdown_string` |
| **BRDValidator** | `markdown_brd`, `features`, `frs`, `evidence` | `{score: float, issues: List[str], needs_revision: bool}` |
| **SkillPackMatcher** | `evidence`, `repo_context`, `dep_data` | `List[Tuple[SkillPack, float]]` |
| **SkillPackExecutor** | `activated_packs`, `repo_path` | `SkillExecutionResult` |

### Pydantic Model Hierarchy

```
ECAOutput
├── readme: str
├── file_tree: Dict
├── classified_files: ClassifiedFiles
└── chunks: List[FileChunk]

RepoEvidence
├── has_http_api, has_grpc, has_database, has_auth: bool
├── has_docker, has_kubernetes: bool
├── has_android, has_ios, has_desktop: bool
├── has_gdpr_mention, has_tests: bool
├── platform: str
├── dep_categories: DepCategories
├── build_tool: str
└── primary_language: str

FeatureExtractionResult
└── features: List[ExtractedFeature]
    ├── id: str (feat-NNN)
    ├── name: str
    ├── description: str
    ├── source_modules: List[str]
    └── confidence: float

FeatureValidationResult
└── validated_features: List[ValidatedFeature]
    ├── id: str (re-indexed)
    ├── name: str (snake_case)
    ├── description: str
    ├── confidence: float
    └── merge_of: List[str]

ProductUnderstandingResult
└── product: ProductProfile
    ├── name: str (snake_case)
    ├── summary: str (≤120 words)
    └── core_capabilities: List[str]

BusinessUnderstandingResult
└── business_context: BusinessContext
    ├── product_type: str
    ├── primary_users: List[str]
    └── core_value: str

FunctionalRequirementsResult
└── functional_requirements: List[FunctionalRequirement]
    ├── id: str (FR-N)
    ├── description: str (SHALL-style)
    ├── linked_feature: str
    └── acceptance_criteria: List[str]

NonFunctionalRequirementsResult
└── non_functional_requirements: List[NonFunctionalRequirement]
    ├── id: str (NFR-N)
    ├── category: Literal["performance", "security", "scalability", "availability"]
    └── description: str

BRDValidationResult
├── score: float (0.0–1.0)
├── issues: List[str]
└── needs_revision: bool (score < 0.85)

ExtractedEntity
├── name: str
├── source_file: str
├── table_name: Optional[str]
├── fields: List[str]
└── entity_type: Literal["jpa_entity", "data_class", "proto_message", "generic_model"]

SkillActivation
├── skill_id: str
├── skill_name: str
├── score: float
├── auto_generated: bool
└── scripts_run: List[str]

SkillExecutionResult
├── activated_skills: List[SkillActivation]
├── additional_features: List[Dict]
├── additional_signals: Dict[str, Any]
└── brd_section_hints: Dict[str, str]
```

---

## Agent Development Patterns

### Pattern 1: Creating a New Analysis Agent

When adding a new analysis agent (e.g., `SecurityAnalysisAgent`), follow this structure:

```python
from pydantic import BaseModel, Field
from typing import List, Literal

# 1. Define output schema in schemas/models.py
class SecurityFinding(BaseModel):
    id: str
    severity: Literal["high", "medium", "low"]
    description: str
    evidence: List[str]

class SecurityAnalysisResult(BaseModel):
    findings: List[SecurityFinding]

# 2. Create the agent module (app/analysis/security_analysis_agent.py)
from app.utils.llm_client import llm_json_call

def analyze_security(context: dict) -> SecurityAnalysisResult:
    prompt = f"Analyze the following codebase for security issues: {context}"
    result = llm_json_call(
        system_prompt="You are a security expert.",
        user_prompt=prompt,
    )
    return SecurityAnalysisResult(**result)

# 3. Register in pipeline/runner.py
# 4. Add API endpoint in api/main.py
```

### Pattern 2: Adding a New File Extractor

To add extraction logic for a new file type (e.g., GraphQL schemas):

```python
# app/eca/graphql_extractor.py
from typing import List, Dict, Any

def extract_graphql_signals(content: str, file_path: str) -> List[Dict[str, Any]]:
    """Extract GraphQL schema definitions and resolvers."""
    signals = []
    # Implementation...
    return signals

# Register in app/eca/extractor.py under the sub_extractors list
```

### Pattern 3: Extending the Language Registry

To add support for a new programming language:

1. Edit [app/eca/config/language_registry.json](app/eca/config/language_registry.json):
```json
"rust": {
  "extensions": [".rs"],
  "role": "backend",
  "entry_points": ["main.rs", "lib.rs"],
  "build_files": ["Cargo.toml", "Cargo.lock"],
  "binary": false,
  "notes": "Rust language support"
}
```

2. No Python changes required — `language_loader.py` auto-reads the registry.

### Pattern 4: Adding a New BRD Section

To add a new section to the generated BRD:

1. Add section builder function in [app/analysis/brd_composer.py](app/analysis/brd_composer.py)
2. Add heading to `REQUIRED_SECTIONS` in [app/analysis/brd_validator.py](app/analysis/brd_validator.py)
3. Update Table of Contents in `_cover()` in `brd_composer.py`

### Pattern 5: Adding a New Skill Pack

To add domain-specific analysis for a new repository type:

1. Create the pack directory:
```
app/skills/packs/my_domain/
├── SKILL.md              ← required (YAML frontmatter + instructions)
├── scripts/
│   └── extractor.py      ← optional, stdlib only, argparse CLI
└── references/
    └── patterns.md       ← optional reference docs
```

2. Write `SKILL.md` with YAML frontmatter:
```yaml
---
name: my_domain
display_name: My Domain Pack
description: Specialized analysis for my domain
version: 1.0.0
detection_signals:
  evidence_flags: [has_http_api]
  dependency_keywords: [my-framework]
  file_patterns: ["**/my_pattern/**"]
scripts:
  - name: extractor
    path: scripts/extractor.py
    args: [--repo-path, "{repo_path}"]
---
```

3. Script contract (if using scripts):
```python
# Must print a single JSON object to stdout:
{
  "features": [{"name": str, "description": str, "confidence": float}],
  "signals":  [{"key": str, "value": any}],
  "hints":    [str]
}
```

No registration code needed — `skill_loader.py` auto-discovers all packs on startup.

---

## Running the Pipeline

### CLI (End-to-End)

```bash
python -m app.pipeline.runner <GITHUB_REPO_URL> [--outdir runtime/pipeline_out]
```

### API Server

```bash
uvicorn app.api.main:app --reload
```

| URL | Description |
|-----|-------------|
| `http://localhost:8000` | Serves the frontend UI |
| `http://localhost:8000/docs` | Interactive Swagger API documentation |
| `http://localhost:8000/health` | Health check endpoint |

### API Endpoints

#### Core Pipeline

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/analyze` | Phase 1 only: Clone + extract context |
| `POST` | `/analyze-and-convert` | Full end-to-end pipeline |
| `POST` | `/convert` | Convert pre-computed payload to MinimalBRD |

#### Granular Agents

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/extract-features` | Run FeatureExtractionAgent |
| `POST` | `/validate-features` | Run FeatureValidator |
| `POST` | `/understand-product` | Run ProductUnderstandingAgent |
| `POST` | `/generate-requirements` | Run FunctionalRequirementGenerator |
| `POST` | `/generate-nfrs` | Run NonFunctionalRequirementGenerator |
| `POST` | `/compose-brd` | Run BRDComposer |
| `POST` | `/validate-brd` | Run BRDValidator |
| `POST` | `/fix-brd` | Run BRDFixLoop |

#### Skill Pack Management

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/skills` | List all available skill packs (curated + generated) |
| `GET` | `/skills/{id}` | Get full details of a specific skill pack |
| `POST` | `/skills/compose` | Manually trigger LLM skill pack composition |
| `PUT` | `/skills/{id}/promote` | Promote a generated pack to stable curated status |

#### Download

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/download/brd-markdown` | Stream BRD as .md |
| `POST` | `/download/brd-docx` | Convert BRD to .docx |
| `POST` | `/download/pipeline-json` | Stream raw pipeline payload as .json |

---

## Configuration

### Environment Variables

Create a `.env` file from `.env.example`:

```env
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_TOKENS=2048

# GPT-5 / o-series model tuning (optional)
OPENAI_JSON_MIN_TOKENS=4096
OPENAI_JSON_TOKEN_MULTIPLIER=3
OPENAI_REASONING_EFFORT=minimal
OPENAI_VERBOSITY=low
```

**Important:** If `OPENAI_API_KEY` is not set, the pipeline runs in **deterministic-only mode**. LLM enrichment and hallucination-pruning steps are silently skipped.

### Language Registry

The [language_registry.json](app/eca/config/language_registry.json) is the **single source of truth** for all language knowledge (40+ languages):
- File extension → language name mapping
- Language role classification (frontend, backend, config, docs)
- Binary and ignored-directory skip lists
- Known application entry-points and build-file names

### Archetype Registry

The [archetype_registry.json](app/analysis/config/archetype_registry.json) drives product archetype detection (13 archetypes):
- Keyword-based voting for archetype classification
- Display names and description fragments for BRD composition
- LLM archetype detection uses this as fallback

---

## Design Principles

1. **Reliability First** — Deterministic pipeline always produces a valid BRD. LLM is optional enrichment.
2. **Data-First** — JSON Schemas defined before code. All inter-stage outputs are Pydantic-validated.
3. **No Hallucination** — LLM prompts supply full structured context. `temperature=0`. Outputs semantically pruned.
4. **Absolute Traceability** — Every feature maps to evidence. Every FR maps to a validated feature.
5. **Repository Isolation** — Each run clones into a unique per-repo directory.
6. **Self-Annealing** — On error or low-quality BRD: Analyze → Patch → Test → Update architecture SOP.
7. **Zero Hardcoded Language Facts** — All language knowledge lives in `language_registry.json`.
8. **Evidence-Grounded Output** — `RepoEvidenceManifest` prevents phantom tech claims in the BRD.
9. **Self-Growing Intelligence** — SkillComposer auto-generates new skill packs for novel repository types.

---

## BRD Validation (9 Dimensions)

The `BRDValidator` scores every generated BRD across 9 dimensions (threshold: 0.85):

| # | Dimension | What is Checked |
|---|-----------|----------------|
| 1 | **Completeness** | All 16 required section headings are present |
| 2 | **Traceability** | Every input feature name and FR-ID appears in the BRD |
| 3 | **No-Hallucination** | BRD references no FR-IDs absent from the input set |
| 4 | **Clarity** | No banned vague phrases (e.g., "seamlessly", "world-class") |
| 5 | **FR Testability** | FR descriptions contain testable verbs (SHALL, MUST, validates) |
| 6 | **NFR Specificity** | NFR SLA targets contain real measurable values |
| 7 | **Stakeholder Specificity** | Stakeholder roles are project-specific, not generic |
| 8 | **Section Depth** | Every section has meaningful content (≥30 words) |
| 9 | **Tech Grounding** | Tech claims (Kubernetes, Docker, GDPR, gRPC, etc.) are backed by `RepoEvidenceManifest` |

**Required BRD Sections (16 total):**
1. Executive Summary · 2. Business Context · 3. Current State Analysis · 4. Stakeholders
5. Functional Requirements · 6. Non-Functional Requirements · 7. Data Requirements
8. Technology Stack · 9. CI/CD Pipeline · 10. Infrastructure · 11. Risk Register
12. Compliance · 13. Acceptance Criteria · 14. Delivery Roadmap · 15. Open Issues
16. Document Approval

---

## LLM Integration Points

OpenAI is used in **multiple optional, non-blocking phases**:

### Phase 2 — Feature Extraction (LLM-primary)
Uses RepoContext (README + structure + snippets) as grounding. Falls back to module-name-based features.

### Phase 2.5 — Semantic Feature Pruning
Removes hallucinated features using README as ground truth.

### Phase 3 — Product Archetype Detection
LLM detects archetype from evidence + features. Falls back to keyword voting.

### Phase 3.5 — LLM Enrichment
- **Feature Descriptions** — Rewrites as SHALL-style sentences
- **Core Value Statement** — ≤30-word value delivery statement
- **Enterprise Artifacts** — Stakeholders, CI/CD, Infra, Data, Compliance, Risks

### Phase 3.7 — BRD Deep Enrichment (7 LLM calls)
Executive Summary, Business Context, Stakeholders, Functional Requirements (batched), NFR SLAs, Delivery Roadmap, Open Issues.

### Phase 1.5 — Skill Composer (fallback)
Auto-generates SKILL.md for novel repository types when no existing pack matches.

All LLM calls go through [app/utils/llm_client.py](app/utils/llm_client.py) which enforces:
- `temperature=0` for deterministic output
- JSON mode for structured parsing
- Supports o1/o3/o4/gpt-5 model families with automatic parameter adaptation
- Graceful fallback to deterministic output on failure

---

## Testing Guidelines

Tests are located in [app/tests/](app/tests/). Run tests with:

```bash
pytest app/tests/ -v
```

Test files:
- `test_pipeline.py` — End-to-end pipeline integration tests
- `test_brd_grounding.py` — BRD evidence grounding validation
- `test_entity_extractor.py` — Entity extraction unit tests
- `test_llm_client.py` — LLM client wrapper tests

Key test patterns:
- **Unit tests** — Test individual functions in isolation
- **Integration tests** — Test pipeline stages end-to-end
- **Deterministic tests** — Compare outputs against known-good baselines

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| No `OPENAI_API_KEY` | Pipeline runs fully deterministically. LLM steps silently skipped. |
| LLM API Error | Individual enrichment calls fall back to deterministic output. Pipeline never blocks. |
| Missing `README` in target repo | System infers purpose from code structure and file signals via priority waterfall. |
| BRD score < 0.85 | `BRDFixLoop` applies up to 2 deterministic repair passes. |
| RepoScanner failure | Raises `RuntimeError` immediately with the scanner's error message. |
| Unknown file extension | `language_loader.py` returns `"unknown"` role; file is still processed as plain text. |
| No skill pack matches | SkillComposer auto-generates one (LLM) or skill stage skipped entirely. |
| Skill script timeout/failure | Caught by executor; empty result returned; pipeline continues. |

---

## Quick Reference for Agents

### Starting Points

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

### Common Imports

```python
# Pipeline runner
from app.pipeline.runner import run_pipeline, run_end_to_end, run_full_pipeline_service

# ECA components
from app.eca.repo_scanner import scan_repository
from app.eca.file_classifier import run_classifier
from app.eca.content_processor import run_content_processor
from app.eca.language_loader import load_language_registry
from app.eca.repo_context_builder import build_repo_context
from app.eca.evidence_manifest import build_evidence_manifest
from app.eca.api_extractor import extract_api_endpoints
from app.eca.dependency_extractor import extract_dependencies
from app.eca.entity_extractor import extract_entities

# Analysis agents
from app.analysis.feature_extraction_agent import extract_features
from app.analysis.feature_validator import validate_features
from app.analysis.product_understanding_agent import understand_product
from app.analysis.business_understanding_agent import understand_business
from app.analysis.functional_requirement_generator import generate_requirements
from app.analysis.non_functional_requirement_generator import generate_nfrs

# BRD composition
from app.analysis.brd_composer import compose_brd
from app.analysis.brd_validator import validate_brd
from app.analysis.brd_fix_loop import run_fix_loop
from app.analysis.brd_enrichment_agent import enrich_brd_context

# Skill Pack system
from app.skills.skill_loader import load_all_skills
from app.skills.skill_matcher import detect_skill_packs
from app.skills.skill_executor import execute_skill_packs
from app.skills.skill_composer import compose_missing_skill

# LLM utilities
from app.utils.llm_client import llm_json_call, llm_text_call
from app.utils.llm_enrichment import (
    enrich_features, enrich_core_value,
    enrich_enterprise_artifacts, prune_hallucinated_features,
    enrich_executive_summary,
)

# Schemas
from app.schemas.models import (
    ECAOutput, FeatureExtractionResult, ValidatedFeature,
    ProductUnderstandingResult, BusinessUnderstandingResult,
    FunctionalRequirementsResult, NonFunctionalRequirementsResult,
    BRDValidationResult, RepoEvidence, SkillExecutionResult,
    ExtractedEntity, EntityExtractionResult,
)
```

---

## Architecture SOP References

- [architecture/pipeline_sop.md](architecture/pipeline_sop.md) — Pipeline Standard Operating Procedure
- [architecture/technical_overview.md](architecture/technical_overview.md) — Technical architecture overview
- [architecture/BRD.md](architecture/BRD.md) — Sample generated BRD for reference

---

*Last updated: 2026-05-28*
