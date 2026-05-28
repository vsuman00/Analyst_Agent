# Analyst Agent

**Analyst Agent** is an enterprise-grade backend system that converts any GitHub repository into a comprehensive Business Requirement Document (BRD). The pipeline is **deterministic-first** — all structural analysis is performed by rule-based agents. **OpenAI** is used selectively in optional enrichment and hallucination-pruning steps to improve quality without altering structural data provenance.

---

## System Architecture

The pipeline uses a multi-layered, 10-stage state-machine architecture to ensure high-fidelity context extraction and absolute data traceability. Both the CLI and API share a single orchestration core (`run_full_pipeline_service`) for consistent, reproducible output.

**Pipeline Flow:**
```
GitHub Repo URL
    → [1] RepoScanner         — clone & file tree
    → [2] FileClassifier      — categorize source files (driven by language_registry.json)
    → [3] ContentProcessor    — chunk & extract content
    → [3.1] Sub-Extractors    — API, Entity, Dependency, Defect signal extraction
    → [3.5] RepoContextBuilder — priority waterfall intent signals
    → [3.6] EvidenceManifest  — structured repo evidence from file system + extractors
    → [4] ContextAggregator & Normalizer
    → [4.5] SkillPackMatcher  — dynamic skill pack detection (threshold 0.5)
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

**3-Layer Architecture (A.N.T.):**

- **Layer 1: Architecture (`architecture/`)** — Technical SOPs in Markdown. Updated before code changes.
- **Layer 2: Navigation (`app/pipeline/`)** — Orchestration layer. Routes data between tools. No complex logic performed directly.
- **Layer 3: Tools (`app/`)** — Deterministic Python scripts. Atomic, Pydantic-validated, and independently testable.

---

## Pipeline State Machine

```
CREATED → INGESTING → ECA_DONE → CONTEXT_READY → NORMALIZED → VALIDATED
        → SKILLS_ACTIVATED → ANALYZED → [LLM_ENRICHED] → BRD_READY
        → VALIDATING → IMPROVING → COMPLETED / FAILED
```

---

## How to Setup and Run

### 1. Prerequisites

- Python 3.9+
- Git (available on `$PATH` for repository cloning)
- An OpenAI API key *(optional — pipeline runs in deterministic-only mode without it)*

### 2. Installation

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows

# Install all dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration

```bash
cp .env.example .env
```

Open `.env` and configure your keys:

```env
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini         # Optional, default: gpt-4o-mini
OPENAI_MAX_TOKENS=2048           # Optional, default: 2048

# GPT-5 / o-series model tuning (optional)
OPENAI_JSON_MIN_TOKENS=4096
OPENAI_JSON_TOKEN_MULTIPLIER=3
OPENAI_REASONING_EFFORT=minimal
OPENAI_VERBOSITY=low
```

> **Note:** If `OPENAI_API_KEY` is not set, the pipeline runs in **deterministic-only mode**. LLM enrichment and hallucination-pruning steps are silently skipped — the pipeline always produces a valid BRD.

### 4. Running the API Server

```bash
uvicorn app.api.main:app --reload
```

| URL | Description |
|---|---|
| `http://localhost:8000` | Serves the frontend UI (`static/index.html`) |
| `http://localhost:8000/docs` | Interactive Swagger API documentation |
| `http://localhost:8000/health` | Health check endpoint |

### 5. Running the CLI (End-to-End)

You can run the full pipeline directly from the terminal without starting the API server:

```bash
python -m app.pipeline.runner <GITHUB_REPO_URL> [--outdir runtime/pipeline_out]
```

**Example:**
```bash
python -m app.pipeline.runner https://github.com/owner/repo --outdir runtime/pipeline_out
```

The final BRD Markdown file will be written to `runtime/pipeline_out/<repo_name>/brd/BRD_<repo_name>.md`.

---

## Dynamic Skill Pack System

The pipeline includes a **non-blocking, signal-driven intelligence layer** that fires between the Evidence Manifest stage and Feature Extraction. It dynamically detects the repository's domain and activates specialized analysis packs.

**5 Seed Packs included:**

| Pack | Domain | Script |
|---|---|---|
| `web_api` | REST/gRPC API analysis | `api_extractor.py` |
| `ml_pipeline` | ML model & training pipeline | `model_extractor.py` |
| `data_platform` | Data pipeline & warehouse | `pipeline_extractor.py` |
| `mobile_app` | Android/iOS screen & permissions | `screen_extractor.py` |
| `cli_tool` | CLI framework analysis | Instructions only |

If no existing pack matches (score < 0.5), the **SkillComposer** auto-generates a new pack via LLM and saves it for future reuse.

---

## LLM Integration

OpenAI is used in **multiple optional, non-blocking phases**:

### Phase 2 — Feature Extraction (LLM-primary)
Uses RepoContext (README + structure + snippets) as grounding for feature extraction. Falls back to module-name-based features if LLM unavailable.

### Phase 2.5 — Semantic Feature Pruning
Removes hallucinated features that are semantically inconsistent with the actual repository context. Uses README as ground truth.

### Phase 3 — Product Archetype Detection
LLM detects product archetype from evidence + features. Falls back to keyword voting via `archetype_registry.json`.

### Phase 3.5 — LLM Enrichment
Enriches specific outputs before BRD composition:

| Enrichment Target | LLM Task | Fallback |
|---|---|---|
| **Feature Descriptions** | Rewrites terse extracted descriptions into precise SHALL-style sentences | Original deterministic description |
| **Core Value Statement** | Writes a ≤30-word value delivery statement from the feature list | Concatenated feature name list |
| **Enterprise Artifacts** | Generates Stakeholders, CI/CD, Infra, Data, Compliance, Risks | Template-based deterministic output |

### Phase 3.7 — BRD Deep Enrichment (7 LLM calls)
Generates detailed, grounded content for Executive Summary, Business Context, Stakeholders, Functional Requirements, NFR SLAs, Delivery Roadmap, and Open Issues.

**Guarantees:**
- All prompts supply the full structured context. `temperature=0` is enforced.
- Supports o1/o3/o4/gpt-5 model families with automatic parameter adaptation.
- If any LLM call fails, the deterministic fallback is used — **the pipeline never blocks on LLM availability**.

---

## Pipeline Stages (Detailed)

### Stage 1: ECA — Extract, Classify, Aggregate
- **RepoScanner**: Clones the target repository into an isolated `<repo_name>/repo/src/` subdirectory. Binary detection and ignored directories are driven by `language_registry.json`.
- **FileClassifier**: Classifies files into `frontend`, `backend`, `config`, `docs`, `unknown` using the language registry.
- **ContentProcessor**: Reads and chunks file content (~3200 chars/chunk), respecting token budgets.
- **Sub-Extractors** (run against content and file system):
  - `api_extractor.py` — Detects API route definitions and gRPC RPC endpoints.
  - `entity_extractor.py` — Identifies domain entities (JPA, Kotlin data class, proto message).
  - `dependency_extractor.py` — Parses dependency manifests (`package.json`, `requirements.txt`, `pom.xml`, `build.gradle`, etc.).
  - `defect_extractor.py` — Scans for TODO/FIXME/HACK markers and hardcoded credentials.
  - `extractor.py` — Orchestrates all sub-extractors into a unified extraction result.

### Stage 1.1: Language Registry (`app/eca/config/language_registry.json`)
The `language_registry.json` is the **single source of truth** for all language knowledge (40+ languages). It governs:
- File extension → language name mapping
- Language role classification (`frontend`, `backend`, `config`, `docs`)
- Binary and ignored-directory skip lists
- Known application entry-points and build-file names

The `language_loader.py` module exposes a pure-read, LRU-cached API over the registry. **No language facts are hardcoded anywhere in the tool layer.**

### Stage 1.5: Context & Evidence
- **RepoContextBuilder**: Priority waterfall (README → package.json → pyproject.toml → Cargo.toml → entry point docstring → `[NO_DOCUMENTATION]`).
- **EvidenceManifest**: Assembles structured evidence about what the repo actually contains (Docker, Kubernetes, HTTP API, gRPC, database, auth, Android, iOS, GDPR mentions, tests).

### Stage 2: Context Intelligence
- **ContextAggregator**: Combines scan data, classified files, and content chunks into modules.
- **ContextNormalizer**: Normalizes into a list of weighted modules (snake_case, dedup, noise removal).
- **ContextValidator**: Validates completeness of the normalized context.

### Stage 2.5: Skill Pack Activation
- **SkillPackMatcher**: Scores all available skill packs against repo evidence using max-of-dimensions algorithm.
- **SkillPackExecutor**: Runs activated pack scripts as isolated subprocesses, collecting domain features and signals.
- **SkillComposer** (fallback): Auto-generates a new skill pack via LLM if no existing pack matches.

### Stage 3: Rule-Based Analysis
- **FeatureExtractionAgent** — LLM-primary extraction with skill features merged and deduped.
- **FeatureValidator** — 3-pass: exact dedup → merge groups → snake_case normalisation.
- **[Phase 2.5] Semantic Pruning** — LLM cross-checks extracted features against README.
- **ProductUnderstandingAgent** — LLM archetype detection with keyword voting fallback.
- **BusinessUnderstandingAgent** — Derives `product_type`, `primary_users`, `core_value`.
- **FunctionalRequirementGenerator** — Maps each validated feature to 1–3 testable FRs with acceptance criteria.
- **NonFunctionalRequirementGenerator** — Generates 5–8 system-level NFRs from tech stack signals.

### Stage 3.5–3.7: LLM Enrichment *(requires OPENAI_API_KEY)*
- Enrich feature descriptions and core value via OpenAI (JSON mode, `temperature=0`).
- Generate enterprise artifact sections (Stakeholders, Data, CI/CD, Infrastructure, Compliance, Risks).
- BRD Deep Enrichment: 7 targeted LLM calls for section-level content generation.
- Managed by `app/utils/llm_enrichment.py` and `app/analysis/brd_enrichment_agent.py`.

### Stage 4: BRD Composition & Validation
- **BRDComposer** — Assembles all structured inputs into a comprehensive enterprise BRD in Markdown (16 required sections). Evidence-aware: checks `RepoEvidenceManifest` before writing platform/infra/compliance claims.
- **BRDValidator** — Scores the BRD across **9 dimensions** (threshold: 0.85). See [BRD Validation](#brd-validation) below.
- **BRDFixLoop** — Applies up to 2 deterministic repair passes if score < 0.85.

### Stage 5: Export
- **DocumentGenerator** — Converts the final BRD Markdown to a professional `.docx` file.
- Output saved to: `runtime/pipeline_out/<repo_name>/brd/BRD_<repo_name>.md`

---

## BRD Validation

The `BRDValidator` scores every generated BRD across **9 equal-weight dimensions** (0.0–1.0 each). The aggregate threshold for passing is **0.85**.

| # | Dimension | What is Checked |
|---|---|---|
| 1 | **Completeness** | All 16 required section headings are present |
| 2 | **Traceability** | Every input feature name and FR-ID appears in the BRD |
| 3 | **No-Hallucination** | BRD references no FR-IDs absent from the input set |
| 4 | **Clarity** | No banned vague phrases (e.g., "seamlessly", "world-class") |
| 5 | **FR Testability** | FR descriptions contain testable verbs (SHALL, MUST, validates, etc.) |
| 6 | **NFR Specificity** | NFR SLA targets contain real measurable values, not placeholders (TBD, Strict) |
| 7 | **Stakeholder Specificity** | Stakeholder roles are project-specific, not generic ("End User", "Admin") |
| 8 | **Section Depth** | Every section has meaningful content (≥30 words; Executive Summary ≥60 words) |
| 9 | **Tech Grounding** | Tech claims (Kubernetes, Docker, GDPR, gRPC, etc.) are backed by `RepoEvidenceManifest` |

**Required BRD Sections (16 total):**
1. Executive Summary · 2. Business Context · 3. Current State Analysis · 4. Stakeholders · 5. Functional Requirements · 6. Non-Functional Requirements · 7. Data Requirements · 8. Technology Stack · 9. CI/CD Pipeline · 10. Infrastructure · 11. Risk Register · 12. Compliance · 13. Acceptance Criteria · 14. Delivery Roadmap · 15. Open Issues · 16. Document Approval

---

## API Endpoints

### Core Pipeline

| Method | Path | Description |
|---|---|---|
| `POST` | `/analyze` | Phase 1 only: Clone + extract context. Returns canonical payload. |
| `POST` | `/analyze-and-convert` | **Full end-to-end**: Stages 1–10. Returns `pipeline`, `brd`, `markdown`, `validation`. |
| `POST` | `/convert` | Convert a pre-computed pipeline payload into a MinimalBRD struct. |

### Granular Agents

| Method | Path | Description |
|---|---|---|
| `POST` | `/extract-features` | Run `FeatureExtractionAgent` |
| `POST` | `/validate-features` | Run `FeatureValidator` |
| `POST` | `/understand-product` | Run `ProductUnderstandingAgent` |
| `POST` | `/generate-requirements` | Run `FunctionalRequirementGenerator` |
| `POST` | `/generate-nfrs` | Run `NonFunctionalRequirementGenerator` |
| `POST` | `/compose-brd` | Run `BRDComposer` |
| `POST` | `/validate-brd` | Run `BRDValidator` (9-dimension scoring) |
| `POST` | `/fix-brd` | Run `BRDFixLoop` |

### Skill Pack Management

| Method | Path | Description |
|---|---|---|
| `GET` | `/skills` | List all available skill packs (curated + generated) |
| `GET` | `/skills/{id}` | Get full details of a specific skill pack |
| `POST` | `/skills/compose` | Manually trigger LLM skill pack composition |
| `PUT` | `/skills/{id}/promote` | Promote a generated pack to stable curated status |

### Download

| Method | Path | Description |
|---|---|---|
| `POST` | `/download/brd-markdown` | Stream BRD as a downloadable `.md` file |
| `POST` | `/download/brd-docx` | Convert BRD to `.docx` and stream for download |
| `POST` | `/download/pipeline-json` | Stream the raw pipeline payload as `.json` |

### Utility

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/` | Serves frontend UI (`static/index.html`) |

---

## Folder Structure

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
├── .env                                    # Local secrets (gitignored)
├── requirements.txt                        # Python dependencies
├── Agents.md                               # Multi-agent collaboration guide
├── Architecture.md                         # Full technical architecture document
└── README.md                               # This file — setup and usage guide
```

---

## Data Schemas

### ECA Output Schema
```json
{
  "readme": "string",
  "file_tree": {},
  "classified_files": {
    "frontend": ["string"],
    "backend": ["string"],
    "config": ["string"],
    "docs": ["string"],
    "unknown": ["string"]
  },
  "chunks": [
    { "file": "string", "content": "string" }
  ]
}
```

### RepoEvidence Schema
```json
{
  "has_http_api": "bool",
  "has_grpc": "bool",
  "has_database": "bool",
  "has_auth": "bool",
  "has_docker": "bool",
  "has_kubernetes": "bool",
  "has_android": "bool",
  "has_ios": "bool",
  "has_desktop": "bool",
  "has_gdpr_mention": "bool",
  "has_tests": "bool",
  "platform": "string",
  "build_tool": "string",
  "primary_language": "string",
  "dep_categories": {
    "database": ["string"],
    "auth": ["string"],
    "grpc": ["string"],
    "infra": ["string"],
    "framework": ["string"],
    "other": ["string"]
  }
}
```

### Normalized Context Schema
```json
{
  "features": [
    { "name": "string", "confidence": "number", "sources": ["string"] }
  ],
  "modules": ["string"],
  "gaps": ["string"]
}
```

---

## Error & Failure Handling

| Scenario | Behavior |
|---|---|
| No `OPENAI_API_KEY` | Pipeline runs fully deterministically. LLM steps silently skipped. |
| LLM API Error | Individual enrichment calls fall back to deterministic output. Pipeline never blocks. |
| Missing `README` in target repo | System infers purpose from code structure and file signals via priority waterfall. |
| BRD score < 0.85 | `BRDFixLoop` applies up to 2 deterministic repair passes (Self-Annealing). |
| RepoScanner failure | Raises `RuntimeError` immediately with the scanner's error message. |
| Unknown file extension | `language_loader.py` returns `"unknown"` role; file is still processed as plain text. |
| No skill pack matches | If LLM available, SkillComposer auto-generates one. Otherwise, skill stage skipped entirely. |
| Skill script timeout/failure | Caught by executor; empty result returned; pipeline continues without augmentation. |

---

## Design & Behavioral Principles

1. **Reliability First** — Deterministic pipeline always produces a valid BRD. LLM is optional enrichment.
2. **Data-First** — JSON Schemas are defined before code. All inter-stage outputs are Pydantic-validated.
3. **No Hallucination** — LLM prompts supply full structured context. `temperature=0`. Outputs semantically pruned.
4. **Absolute Traceability** — Every feature maps to evidence. Every FR maps to a validated feature. `BRDValidator` enforces this across 9 scoring dimensions.
5. **Repository Isolation** — Each run clones into a unique per-repo directory. Successive runs never cross-contaminate.
6. **Self-Annealing** — On error or low-quality BRD: Analyze → Patch → Test → Update architecture SOP.
7. **Zero Hardcoded Language Facts** — All 40+ languages live in `language_registry.json`. All 13 archetypes live in `archetype_registry.json`. Adding support requires only a JSON entry.
8. **Evidence-Grounded Output** — `RepoEvidenceManifest` is assembled from actual file system inspection. BRD sections check evidence flags before writing platform/infra/compliance content.
9. **Self-Growing Intelligence** — SkillComposer auto-generates new skill packs for novel repository types. Generated packs are idempotent and promotable to stable packs.

---

## Testing

Tests are located in `app/tests/`. Run tests with:

```bash
pytest app/tests/ -v
```

Test files:
- `test_pipeline.py` — End-to-end pipeline integration tests
- `test_brd_grounding.py` — BRD evidence grounding validation
- `test_entity_extractor.py` — Entity extraction unit tests
- `test_llm_client.py` — LLM client wrapper tests

---

*Last updated: 2026-05-28*
