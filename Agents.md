# Agents.md — Multi-Agent Collaboration Guide

This document explains how multiple agents can collaborate on developing and extending the **Analyst Agent** project. It provides an overview of the system architecture, key interfaces, development patterns, and guidelines for agents working on this codebase.

---

## Project Overview

**Analyst Agent** is an enterprise-grade backend system that converts any GitHub repository into a comprehensive Business Requirement Document (BRD). The pipeline follows a **deterministic-first** approach — all structural analysis is performed by rule-based agents, with OpenAI used selectively in optional enrichment and hallucination-pruning steps.

**Core Capabilities:**
- Clone and analyze any public GitHub repository
- Classify files by language and role (frontend, backend, config, docs)
- Extract features, entities, dependencies, and API routes
- Generate functional and non-functional requirements
- Compose a validated 16-section BRD document
- Export to Markdown or Word (.docx)

---

## System Architecture

### 10-Stage Pipeline Flow

```
GitHub Repo URL
    → [1] RepoScanner         — clone & file tree
    → [2] FileClassifier      — categorize source files (driven by language_registry.json)
    → [3] ContentProcessor    — chunk & extract content
    → [3.1] Sub-Extractors    — API, Entity, Dependency, Defect signal extraction
    → [4] ContextAggregator & Normalizer
    → [5] FeatureExtractionAgent
    → [6] FeatureValidator
    → [6.5] Semantic Feature Pruning (LLM, optional)
    → [7] ProductUnderstandingAgent
    → [8] FunctionalRequirementGenerator
    → [9] NonFunctionalRequirementGenerator
    → [3.5] LLM Enrichment (optional)
    → [3.6] BusinessUnderstandingAgent
    → [10] BRDComposer → BRDFixLoop → BRD (.md / .docx)
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
        → ANALYZED → [LLM_ENRICHED] → BRD_READY → VALIDATING → IMPROVING
        → COMPLETED / FAILED
```

---

## Directory Structure

```
Analyst-Agent/
├── app/
│   ├── api/
│   │   └── main.py                         # FastAPI entry point — all routes
│   ├── pipeline/
│   │   └── runner.py                       # Master orchestrator (run_pipeline + run_end_to_end)
│   ├── eca/                                # Stage 1: Extract, Classify, Aggregate
│   │   ├── repo_scanner.py                 # Clone & file-tree scan
│   │   ├── file_classifier.py              # Extension → role classification
│   │   ├── content_processor.py            # Chunked file content reader
│   │   ├── language_loader.py              # Pure-read API over language_registry.json (LRU-cached)
│   │   ├── extractor.py                    # Sub-extractor orchestrator
│   │   ├── api_extractor.py                # Detects API routes / endpoint patterns
│   │   ├── entity_extractor.py             # Identifies domain entities & data models
│   │   ├── dependency_extractor.py         # Parses dependency manifests
│   │   ├── defect_extractor.py             # Scans TODO/FIXME/HACK quality markers
│   │   ├── repo_context_builder.py         # Rich context extraction with README, tech stack, snippets
│   │   └── config/
│   │       └── language_registry.json      # Single source of truth for all language knowledge
│   ├── context/                            # Stage 2: Context Intelligence
│   │   ├── aggregator.py                   # Combines scan data, classified files, content chunks
│   │   ├── normalizer.py                   # Normalizes into weighted modules
│   │   └── validator.py                    # Validates completeness of normalized context
│   ├── analysis/                           # Stages 3–4: Analysis & Composition
│   │   ├── feature_extraction_agent.py     # Scans codebase against signal registry
│   │   ├── feature_validator.py            # Merges overlapping features, deduplicates
│   │   ├── feature_interpretation_agent.py  # Maps raw signals to evidence
│   │   ├── business_understanding_agent.py # Derives product_type, primary_users, core_value
│   │   ├── product_understanding_agent.py  # Derives product archetype and core capabilities
│   │   ├── archetype_loader.py             # Loads product archetype definitions
│   │   ├── functional_requirement_generator.py # Maps features to testable FRs
│   │   ├── non_functional_requirement_generator.py # Generates system-level NFRs
│   │   ├── payload_converter.py            # Converts payload → MinimalBRD struct
│   │   ├── brd_composer.py                 # Assembles all inputs into enterprise BRD
│   │   ├── brd_enrichment_agent.py         # LLM enrichment orchestrator (Phase 3.5/3.7)
│   │   ├── brd_validator.py                # 8-dimension BRD quality scorer
│   │   ├── brd_fix_loop.py                 # Self-annealing repair loop (max 2 passes)
│   │   ├── fix_loop.py                     # Low-level fix helpers
│   │   └── document_generator.py           # Markdown → .docx export
│   ├── utils/
│   │   ├── llm_client.py                   # OpenAI API wrapper (retry, JSON mode, temperature=0)
│   │   └── llm_enrichment.py               # LLM enrichment + hallucination pruning
│   ├── output/
│   │   └── final_output_builder.py         # Canonical payload builder
│   ├── schemas/
│   │   └── models.py                       # Pydantic models and data contracts
│   ├── validation/                         # Validation utilities
│   └── tests/                              # Deterministic test cases
├── architecture/
│   ├── pipeline_sop.md                     # Pipeline Standard Operating Procedure
│   ├── technical_overview.md               # Technical architecture overview
│   └── BRD.md                              # Sample generated BRD
├── runtime/
│   └── pipeline_out/                       # All generated BRD artifacts (.md, .docx)
├── static/
│   └── index.html                          # Frontend UI
├── .env.example                            # Environment variable template
├── requirements.txt
└── Agents.md                              # This file
```

---

## Key Interfaces & Data Contracts

All inter-module communication uses Pydantic models defined in [app/schemas/models.py](app/schemas/models.py).

### Core Input/Output Schemas

| Module | Input | Output |
|--------|-------|--------|
| **RepoScanner** | `repo_url`, `dest_dir` | `{repo_name, files, readme, file_tree}` |
| **FileClassifier** | `scan_data` | `{classified_files: {frontend, backend, config, docs, unknown}}` |
| **ContentProcessor** | `classified_data`, `dest_repo_dir` | `{chunks: [{file, content}]}` |
| **FeatureExtractionAgent** | `normalized_modules`, `chunks_list`, `repo_context` | `{features: [ExtractedFeature]}` |
| **FeatureValidator** | `raw_features` | `{validated_features: [ValidatedFeature]}` |
| **ProductUnderstandingAgent** | `validated_features`, `repo_context` | `{product: {name, summary, core_capabilities}}` |
| **FunctionalRequirementGenerator** | `validated_features` | `{functional_requirements: [FunctionalRequirement]}` |
| **NonFunctionalRequirementGenerator** | `system_type`, `tech_stack` | `{non_functional_requirements: [NonFunctionalRequirement]}` |
| **BRDComposer** | `business_context`, `features`, `frs`, `nfrs` | `markdown_string` |
| **BRDValidator** | `markdown_brd` | `{score: float, issues: List[str], needs_revision: bool}` |

### Pydantic Model Hierarchy

```
ECAOutput
├── readme: str
├── file_tree: Dict
├── classified_files: ClassifiedFiles
└── chunks: List[FileChunk]

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
```

---

## Agent Development Patterns

### Pattern 1: Creating a New Analysis Agent

When adding a new analysis agent (e.g., `SecurityAnalysisAgent`), follow this structure:

```python
from pydantic import BaseModel, Field
from typing import List

# 1. Define output schema in schemas/models.py
class SecurityFinding(BaseModel):
    id: str
    severity: Literal["high", "medium", "low"]
    description: str
    evidence: List[str]

class SecurityAnalysisResult(BaseModel):
    findings: List[SecurityFinding]

# 2. Create the agent module
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

1. Update `BRD_SECTIONS` list in [app/analysis/brd_composer.py](app/analysis/brd_composer.py)
2. Add section template to the composition logic
3. Update `BRDValidator` dimensions if needed (in [app/analysis/brd_validator.py](app/analysis/brd_validator.py))

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

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/analyze` | Phase 1 only: Clone + extract context |
| `POST` | `/analyze-and-convert` | Full end-to-end pipeline |
| `POST` | `/convert` | Convert pre-computed payload to MinimalBRD |
| `POST` | `/extract-features` | Run FeatureExtractionAgent |
| `POST` | `/validate-features` | Run FeatureValidator |
| `POST` | `/understand-product` | Run ProductUnderstandingAgent |
| `POST` | `/generate-requirements` | Run FunctionalRequirementGenerator |
| `POST` | `/generate-nfrs` | Run NonFunctionalRequirementGenerator |
| `POST` | `/compose-brd` | Run BRDComposer |
| `POST` | `/validate-brd` | Run BRDValidator |
| `POST` | `/fix-brd` | Run BRDFixLoop |
| `POST` | `/download/brd-markdown` | Stream BRD as .md |
| `POST` | `/download/brd-docx` | Convert BRD to .docx |

---

## Configuration

### Environment Variables

Create a `.env` file from `.env.example`:

```env
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_TOKENS=2048
```

**Important:** If `OPENAI_API_KEY` is not set, the pipeline runs in **deterministic-only mode**. LLM enrichment and hallucination-pruning steps are silently skipped.

### Language Registry

The [language_registry.json](app/eca/config/language_registry.json) is the **single source of truth** for all language knowledge:
- File extension → language name mapping
- Language role classification (frontend, backend, config, docs)
- Binary and ignored-directory skip lists
- Known application entry-points and build-file names

---

## Design Principles

1. **Reliability First** — Deterministic pipeline always produces a valid BRD. LLM is optional enrichment.
2. **Data-First** — JSON Schemas defined before code. All inter-stage outputs are Pydantic-validated.
3. **No Hallucination** — LLM prompts supply full structured context. `temperature=0`. Outputs semantically pruned.
4. **Absolute Traceability** — Every feature maps to evidence. Every FR maps to a validated feature.
5. **Repository Isolation** — Each run clones into a unique `runner_<repo_name>/` directory.
6. **Self-Annealing** — On error or low-quality BRD: Analyze → Patch → Test → Update architecture SOP.
7. **Zero Hardcoded Language Facts** — All language knowledge lives in `language_registry.json`.

---

## BRD Validation (8 Dimensions)

The `BRDValidator` scores every generated BRD across 8 dimensions (threshold: 0.85):

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

**Required BRD Sections (16 total):**
1. Executive Summary · 2. Business Context · 3. Current State Analysis · 4. Stakeholders
5. Functional Requirements · 6. Non-Functional Requirements · 7. Data Requirements
8. Technology Stack · 9. CI/CD Pipeline · 10. Infrastructure · 11. Risk Register
12. Compliance · 13. Acceptance Criteria · 14. Delivery Roadmap · 15. Open Issues
16. Document Approval

---

## LLM Integration Points

OpenAI is used in **two optional, non-blocking phases**:

### Phase 2.5 — Semantic Feature Pruning
Removes hallucinated features that are semantically inconsistent with the actual repository context. Runs after `FeatureValidator` and before `ProductUnderstandingAgent`.

### Phase 3.5/3.7 — LLM Enrichment
Enriches three specific outputs before BRD composition:
- **Feature Descriptions** — Rewrites terse extracted descriptions into precise SHALL-style sentences
- **Core Value Statement** — Writes a ≤30-word value delivery statement
- **Enterprise Artifacts** — Generates Data Strategy, Infrastructure, Risk Register sections

All LLM calls go through [app/utils/llm_client.py](app/utils/llm_client.py) which enforces:
- `temperature=0` for deterministic output
- JSON mode for structured parsing
- Graceful fallback to deterministic output on failure

---

## Testing Guidelines

Tests are located in [app/tests/](app/tests/). Run tests with:

```bash
pytest app/tests/ -v
```

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
| Missing `README` in target repo | System infers purpose from code structure and file signals. |
| BRD score < 0.85 | `BRDFixLoop` applies up to 2 deterministic repair passes. |
| RepoScanner failure | Raises `RuntimeError` immediately with the scanner's error message. |
| Unknown file extension | `language_loader.py` returns `"unknown"` role; file is still processed as plain text. |

---

## Quick Reference for Agents

### Starting Points

| Task | File to Modify |
|------|---------------|
| Add new language support | `app/eca/config/language_registry.json` |
| Add new analysis agent | `app/analysis/<agent_name>.py` |
| Add new file extractor | `app/eca/<extractor_name>.py` |
| Modify BRD structure | `app/analysis/brd_composer.py` |
| Modify validation rules | `app/analysis/brd_validator.py` |
| Add new API endpoint | `app/api/main.py` |
| Add/modify Pydantic schemas | `app/schemas/models.py` |

### Common Imports

```python
# Pipeline runner
from app.pipeline.runner import run_pipeline, run_end_to_end

# ECA components
from app.eca.repo_scanner import scan_repository
from app.eca.file_classifier import run_classifier
from app.eca.content_processor import run_content_processor
from app.eca.language_loader import load_language_registry

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

# LLM utilities
from app.utils.llm_client import llm_json_call, llm_text_call
from app.utils.llm_enrichment import enrich_features, enrich_core_value

# Schemas
from app.schemas.models import ECAOutput, FeatureExtractionResult, ValidatedFeature
```

---

## Architecture SOP References

- [architecture/pipeline_sop.md](architecture/pipeline_sop.md) — Pipeline Standard Operating Procedure
- [architecture/technical_overview.md](architecture/technical_overview.md) — Technical architecture overview
- [architecture/BRD.md](architecture/BRD.md) — Sample generated BRD for reference

---

*Last updated: 2026-05-17*