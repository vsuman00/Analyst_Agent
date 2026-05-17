# Graph Report - .  (2026-05-17)

## Corpus Check
- Corpus is ~47,167 words - fits in a single context window. You may not need a graph.

## Summary
- 581 nodes · 892 edges · 44 communities detected
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 123 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `BRDValidationResult` - 20 edges
2. `compose_brd()` - 19 edges
3. `Pipeline Runner (Orchestrator)` - 17 edges
4. `AnalysisFeature` - 12 edges
5. `Requirement` - 12 edges
6. `MinimalBRD` - 12 edges
7. `_load_registry()` - 12 edges
8. `validate_brd()` - 11 edges
9. `TestEvidenceManifest` - 11 edges
10. `ValidatedFeature` - 11 edges

## Surprising Connections (you probably didn't know these)
- `FeatureExtractionAgent` --signals interpreted by--> `FeatureInterpretationAgent`  [AMBIGUOUS]
  README.md → Agents.md
- `brd_fix_loop.py — Layer 3 Tool -------------------------------- BRDFixLoop  Inpu` --uses--> `BRDValidationResult`  [INFERRED]
  app/analysis/brd_fix_loop.py → app/schemas/models.py
- `Apply deterministic fixes based on validation issues.` --uses--> `BRDValidationResult`  [INFERRED]
  app/analysis/brd_fix_loop.py → app/schemas/models.py
- `Run the validation/fix loop.     Returns:       {         "final_markdown": str,` --uses--> `BRDValidationResult`  [INFERRED]
  app/analysis/brd_fix_loop.py → app/schemas/models.py
- `brd_validator.py — Layer 3 Tool --------------------------------- BRDValidator` --uses--> `BRDValidationResult`  [INFERRED]
  app/analysis/brd_validator.py → app/schemas/models.py

## Hyperedges (group relationships)
- **ECA Stage (Extract, Classify, Aggregate)** — repo-scanner, file-classifier, content-processor, sub-extractors, language-registry, language-loader, repo-context-builder [INFERRED]
- **Context Intelligence Stage** — context-aggregator, context-normalizer, context-validator, context-builder [INFERRED]
- **Rule-Based Analysis Stage** — feature-extraction-agent, feature-validator, semantic-feature-pruning, product-understanding-agent, business-understanding-agent, functional-requirement-generator, non-functional-requirement-generator, feature-interpretation-agent [INFERRED]
- **BRD Composition & Validation Stage** — brd-composer, brd-validator, brd-fix-loop, brd-enrichment-agent, document-generator [INFERRED]
- **A.N.T. Architecture Layer** — pipeline-sop-doc, technical-overview-doc, pipeline-runner, fastapi-api-layer, repo-scanner, file-classifier, content-processor, context-aggregator [INFERRED]
- **LLM Integration Points** — semantic-feature-pruning, brd-enrichment-agent, llm-client, llm-enrichment [INFERRED]
- **Sub-Extractor Group** — api-extractor, entity-extractor, dependency-extractor, defect-extractor, sub-extractors [INFERRED]
- **Data Contract System** — pydantic-models, eca-output-schema, normalized-context-schema, payload-converter, final-output-builder [INFERRED]
- **Validation Subsystem** — context-validator, feature-validator, brd-validator, brd-fix-loop [INFERRED]
- **Project Documentation Corpus** — pipeline-sop-doc, technical-overview-doc, brd-sample-doc, prd-v3-doc, task-plan-blast, itemae-brd [INFERRED]

## Communities

### Community 0 - "Business Understanding & Models"
Cohesion: 0.04
Nodes (80): BaseModel, business_understanding_agent.py — Layer 3 Tool ---------------------------------, Derive business context deterministically from features and system type., understand_business(), Classify a file by consulting the language registry., # NOTE: Extension-to-role mapping is now fully driven by the language registry., _build_rich_context_str(), _calibrate_confidence() (+72 more)

### Community 1 - "FastAPI Endpoints"
Cohesion: 0.04
Nodes (45): analyze_and_convert(), AnalyzeRequest, compose_brd_endpoint(), ComposeBRDRequest, convert_payload(), ConvertRequest, download_brd_docx(), download_brd_markdown() (+37 more)

### Community 2 - "Semantic Pipeline Components"
Cohesion: 0.06
Nodes (38): API Extractor, Archetype Loader, Archetype Registry, BRDComposer, BRD Enrichment Agent (LLM Phase 3.5), BRDFixLoop (self-annealing repair), BRDValidator (8-dimension scorer), BusinessUnderstandingAgent (+30 more)

### Community 3 - "Language Registry Loader"
Cohesion: 0.1
Nodes (31): _build_binary_set(), _build_build_file_names(), _build_config_ext_set(), _build_doc_ext_set(), _build_entry_points(), _build_ext_to_language(), _build_ignore_dirs(), describe() (+23 more)

### Community 4 - "Repo Context Builder"
Cohesion: 0.11
Nodes (29): build_intent_signals(), build_repo_context(), _detect_tech_stack(), _extract_cargo(), _extract_entry_point_docstring(), _extract_package_json(), _extract_pyproject(), _extract_readme() (+21 more)

### Community 5 - "BRD Composition Logic"
Cohesion: 0.16
Nodes (23): compose_brd(), _cover(), _display(), _has_keyword(), _moscow(), brd_composer.py — Enterprise BRD Composer (16-section) Produces a professional B, _s10_infra(), _s11_risks() (+15 more)

### Community 6 - "BRD Grounding Tests (Core)"
Cohesion: 0.13
Nodes (10): _empty_api_data(), _empty_dep_data(), test_brd_grounding.py — Regression suite for BRD accuracy / evidence-groundednes, Verify that enrich_functional_requirements processes FRs in batches., Integration test: validate_brd should respect evidence in 9th dimension., A minimal BRD claiming Kubernetes for testing grounding., Unit tests for build_evidence_manifest using a temp directory., TestEvidenceManifest (+2 more)

### Community 7 - "Pydantic Data Models"
Cohesion: 0.2
Nodes (23): AnalysisFeature, MinimalBRD, A product-level feature derived deterministically from the final payload., A functional requirement derived from a detected feature or validation output., Minimal, structured BRD derived purely from the pipeline's final payload., Requirement, build_brd(), _derive_gaps() (+15 more)

### Community 8 - "BRD Validator"
Cohesion: 0.12
Nodes (21): brd_validator.py — Layer 3 Tool --------------------------------- BRDValidator, Check that every input feature name and every FR-ID appears in the BRD.     Part, Check that BRD does not contain FR-IDs absent from the input set.     Feature na, Penalise presence of banned vague phrases.     Each violation deducts a fixed 0., Check that FR descriptions contain testable verbs (SHALL, MUST, validates, etc.), Check that NFR SLA targets contain actual measurable values,     not placeholder, Check that the Stakeholders section contains project-specific roles,     not jus, Check that each required section has meaningful content (≥ 30 words).     Also c (+13 more)

### Community 9 - "Product Understanding"
Cohesion: 0.2
Nodes (20): ProductProfile, ProductUnderstandingResult, Structured product understanding derived purely from validated features.      Ru, Top-level output envelope for ProductUnderstandingAgent., _build_summary(), _derive_capabilities(), _detect_archetype(), _llm_detect_archetype() (+12 more)

### Community 10 - "BRD Grounding Tests (Loader)"
Cohesion: 0.15
Nodes (11): _load_brd(), Golden assertions against previously-generated BRD files.     Tests fail if BRD, Android repo BRDs must NOT claim Kubernetes infrastructure., Android repo BRDs should identify the platform as mobile/Android., Weather app BRD must NOT write a GDPR compliance block unless the README, Spring PetClinic is a web app — its BRD should mention REST API., Spring PetClinic uses JPA/HSQL — the data requirements section should reflect th, OD System Analyser BRD should not fabricate GDPR compliance if not in README. (+3 more)

### Community 11 - "BRD Grounding Tests (Extended)"
Cohesion: 0.18
Nodes (8): Unit tests for the _score_tech_grounding dimension., Kubernetes in BRD + evidence says has_kubernetes=True → passes., Kubernetes in BRD but evidence says has_kubernetes=False → fails., GDPR in BRD but evidence says has_gdpr_mention=False → fails., Android in BRD + evidence has_android=True → passes., REST API in BRD but evidence says has_http_api=False → fails., A BRD with no technology terms always passes grounding check., TestTechGrounding

### Community 12 - "BRD Enrichment Agent"
Cohesion: 0.35
Nodes (13): enrich_brd_context(), enrich_business_context(), enrich_executive_summary(), enrich_functional_requirements(), enrich_nfrs(), enrich_open_issues(), enrich_roadmap(), enrich_stakeholders() (+5 more)

### Community 13 - "LLM Enrichment Module"
Cohesion: 0.16
Nodes (13): enrich_core_value(), enrich_enterprise_artifacts(), enrich_executive_summary(), enrich_features(), _fallback_core_value(), _fallback_summary(), prune_hallucinated_features(), llm_enrichment.py — Layer 3 Tool ---------------------------------- LLM Enrichme (+5 more)

### Community 14 - "Document Generator (DOCX)"
Cohesion: 0.22
Nodes (12): _add_hr(), _apply_inline_markup(), _is_separator_row(), markdown_to_docx(), _parse_table_row(), document_generator.py — Layer 3 Tool -------------------------------------- Docu, Parse inline markdown (**bold**, _italic_, `code`) and add styled runs.     All, Parse a Markdown table row into a list of cell strings. (+4 more)

### Community 15 - "Archetype Loader"
Cohesion: 0.21
Nodes (11): _build_domain_signals(), get_domain_signals(), list_archetypes(), _load_registry(), archetype_loader.py — Analysis Config Registry Engine --------------------------, Force-clear all caches so that a modified archetype_registry.json     is re-read, Load the archetype registry JSON once and cache it for the process lifetime., Convert the JSON registry into the DOMAIN_SIGNALS shape expected by     ProductU (+3 more)

### Community 16 - "LLM Client"
Cohesion: 0.23
Nodes (11): _call_with_retry(), _completion_token_limit(), _format_usage(), llm_json_call(), llm_text_call(), llm_client.py — Layer 3 Utility --------------------------------- Centralised Op, Return compact token usage for diagnostics without depending on SDK internals., GPT-5-style chat completion limits include hidden reasoning plus visible text. (+3 more)

### Community 17 - "Evidence Manifest"
Cohesion: 0.23
Nodes (11): build_evidence_manifest(), _categorize_deps(), _detect_platform(), _log_manifest_summary(), evidence_manifest.py — ECA Layer 3 Tool ----------------------------------------, Derive the primary platform string from evidence — without any domain keyword li, Build the RepoEvidenceManifest from actual repo file system + extractor outputs., Print a one-line summary of the manifest for pipeline logs. (+3 more)

### Community 18 - "LLM Client Tests"
Cohesion: 0.4
Nodes (2): FakeCompletions, LLMClientTests

### Community 19 - "Pipeline Runner"
Cohesion: 0.28
Nodes (8): log_stage(), run_full_pipeline.py — Master Orchestration Script -----------------------------, Phase 1 pipeline: clone → scan → classify → chunk → aggregate → normalize → vali, Attempt LLM enrichment. Returns enriched features, updated business context, and, Helper function to cleanly log pipeline stages., run_end_to_end(), run_pipeline(), _try_enrich()

### Community 20 - "BRD Fix Loop Logic"
Cohesion: 0.28
Nodes (7): _apply_clarity_pass(), _build_traceability_appendix(), fix_loop.py — Layer 3 Tool ---------------------------- FixLoop  Deterministic s, Inject a Traceability Matrix appendix at the end of the BRD for any     features, Run up to MAX_ITERATIONS repair passes on the BRD.      Returns a dict with keys, Replace each banned vague phrase with its precise alternative.     Only operates, run_fix_loop()

### Community 21 - "Entity Extractor"
Cohesion: 0.32
Nodes (7): extract_entities(), _extract_kotlin_fields(), entity_extractor.py — Phase 3 Extractor ----------------------------------------, Extract parameter names from a Kotlin data class constructor., Return a relative path string for display., Scan a repository directory for domain entity definitions.      Returns a dict w, _relative_path()

### Community 22 - "Repo Scanner"
Cohesion: 0.32
Nodes (7): clone_repository(), is_binary(), # NOTE: IGNORE_DIRS and BINARY_EXTS are now loaded from the language registry., Return True if the file should be skipped (binary extension or unreadable conten, Clones the repository and returns True if successful., Clones and scans a repository, returning metadata matching the output schema., scan_repository()

### Community 23 - "Defect Extractor"
Cohesion: 0.38
Nodes (6): extract_defects(), defect_extractor.py — Phase 3 Extractor ----------------------------------------, Check if this file/dir should be skipped., Scan a repository directory for known defects and code smells.      Returns a di, _relative_path(), _should_skip()

### Community 24 - "BRD Fix Loop Orchestrator"
Cohesion: 0.4
Nodes (5): _apply_fixes(), brd_fix_loop.py — Layer 3 Tool -------------------------------- BRDFixLoop  Inpu, Apply deterministic fixes based on validation issues., Run the validation/fix loop.     Returns:       {         "final_markdown": str,, run_fix_loop()

### Community 25 - "Dependency Extractor"
Cohesion: 0.4
Nodes (5): _categorize_dep(), extract_dependencies(), dependency_extractor.py — Phase 3 Extractor ------------------------------------, Scan a repository directory for build files and extract dependency metadata., Assign a category based on Maven group/artifact names.

### Community 26 - "File Classifier"
Cohesion: 0.5
Nodes (4): classify_file(), Classify a file into a category using path heuristics + language registry., # NOTE: All language-specific data (extensions, entry points) is loaded from, run_classifier()

### Community 27 - "API Extractor"
Cohesion: 0.5
Nodes (4): extract_api_endpoints(), api_extractor.py — Phase 3 Extractor --------------------------------------- Ext, Scan a repository directory for REST endpoints and gRPC RPC definitions., _relative_path()

### Community 28 - "ECA Extractor Orchestrator"
Cohesion: 0.7
Nodes (4): build_file_tree(), classify_file(), extract_eca(), is_text_file()

### Community 29 - "Context Aggregator"
Cohesion: 0.67
Nodes (3): aggregate_context(), determine_module_name(), Determines the module name deterministically based on folder structure.     File

### Community 30 - "Context Normalizer"
Cohesion: 0.67
Nodes (3): normalize_context(), Standardize a module name to snake_case format., standardize_name()

### Community 31 - "Final Output Builder"
Cohesion: 0.5
Nodes (2): build_final_output(), Combines all partial outputs into the final deterministic schema.

### Community 32 - "Pipeline Integration Tests"
Cohesion: 1.0
Nodes (2): run_pipeline(), setup_dummy_repo()

### Community 33 - "Content Processor"
Cohesion: 1.0
Nodes (2): process_file(), run_content_processor()

### Community 34 - "A.N.T. Architecture Docs"
Cohesion: 0.67
Nodes (3): A.N.T. 3-Layer Architecture, BLAST Task Plan (5-Phase), Technical Overview Document

### Community 35 - "BRD Output Samples"
Cohesion: 0.67
Nodes (3): BRD Document Output (.md/.docx), Sample BRD (architecture/BRD.md), Itemae Twitter Clone BRD (Sample)

### Community 36 - "Context Validator"
Cohesion: 1.0
Nodes (0): 

### Community 37 - "Context Builder"
Cohesion: 1.0
Nodes (0): 

### Community 38 - "Pipeline State Machine"
Cohesion: 1.0
Nodes (2): Pipeline State Machine, PRD v3 Document

### Community 39 - "Package Init"
Cohesion: 1.0
Nodes (0): 

### Community 40 - "Test Rationale (Isolated)"
Cohesion: 1.0
Nodes (1): Create a minimal fake repo directory.

### Community 41 - "System Overview"
Cohesion: 1.0
Nodes (1): Analyst Agent System

### Community 42 - "ECA Output Schema"
Cohesion: 1.0
Nodes (1): ECA Output Schema

### Community 43 - "Normalized Context Schema"
Cohesion: 1.0
Nodes (1): Normalized Context Schema

## Ambiguous Edges - Review These
- `FeatureExtractionAgent` → `FeatureInterpretationAgent`  [AMBIGUOUS]
   · relation: signals interpreted by

## Knowledge Gaps
- **181 isolated node(s):** `run_full_pipeline.py — Master Orchestration Script -----------------------------`, `Attempt LLM enrichment. Returns enriched features, updated business context, and`, `Helper function to cleanly log pipeline stages.`, `Phase 1 pipeline: clone → scan → classify → chunk → aggregate → normalize → vali`, `Determines the module name deterministically based on folder structure.     File` (+176 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Context Validator`** (2 nodes): `validator.py`, `validate_context()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Context Builder`** (2 nodes): `builder.py`, `analyze_context()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Pipeline State Machine`** (2 nodes): `Pipeline State Machine`, `PRD v3 Document`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Test Rationale (Isolated)`** (1 nodes): `Create a minimal fake repo directory.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `System Overview`** (1 nodes): `Analyst Agent System`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `ECA Output Schema`** (1 nodes): `ECA Output Schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Normalized Context Schema`** (1 nodes): `Normalized Context Schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `FeatureExtractionAgent` and `FeatureInterpretationAgent`?**
  _Edge tagged AMBIGUOUS (relation: signals interpreted by) - confidence is low._
- **Why does `BRDValidationResult` connect `Business Understanding & Models` to `BRD Fix Loop Orchestrator`, `BRD Validator`, `BRD Fix Loop Logic`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Why does `ProductProfile` connect `Product Understanding` to `Business Understanding & Models`?**
  _High betweenness centrality (0.012) - this node is a cross-community bridge._
- **Why does `ProductUnderstandingResult` connect `Product Understanding` to `Business Understanding & Models`?**
  _High betweenness centrality (0.012) - this node is a cross-community bridge._
- **Are the 17 inferred relationships involving `BRDValidationResult` (e.g. with `brd_fix_loop.py — Layer 3 Tool -------------------------------- BRDFixLoop  Inpu` and `Apply deterministic fixes based on validation issues.`) actually correct?**
  _`BRDValidationResult` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `AnalysisFeature` (e.g. with `payload_converter.py — Layer 3 Tool ------------------------------------- Conver` and `Infer a feature category from its source file paths deterministically.`) actually correct?**
  _`AnalysisFeature` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `run_full_pipeline.py — Master Orchestration Script -----------------------------`, `Attempt LLM enrichment. Returns enriched features, updated business context, and`, `Helper function to cleanly log pipeline stages.` to the rest of the system?**
  _181 weakly-connected nodes found - possible documentation gaps or missing edges._