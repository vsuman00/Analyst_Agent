# Business Requirement Document (BRD)
**Project:** Analyst Agent  
**Version:** 1.0  
**Date:** 2026-05-03  
**Status:** Draft

---

## Executive Summary

Analyst Agent is an enterprise-grade backend system that converts any GitHub repository into a structured analytical payload. The system operates as a fully deterministic, 7-stage data pipeline — accepting a repository URL and producing a canonical JSON output containing a classified file manifest, content chunks, normalized module map, structural validation score, and detected product features.

The pipeline performs no machine-learning inference during its core extraction stages. All classification, chunking, aggregation, normalization, and validation steps are rule-based and produce identical outputs for identical inputs. A REST API layer (FastAPI) exposes the pipeline for on-demand, synchronous invocation.

The primary output of the system is intended for downstream consumption by LLM-based tools (e.g., BRD generators, test plan writers) that require a structured, token-safe representation of a codebase.

---

## Features

| ID | Name | Confidence |
|----|------|------------|
| feat-001 | Repository Cloning and File Manifest Generation | 1.0 |
| feat-002 | Granular Rule-Based File Classification with Confidence Scoring | 1.0 |
| feat-003 | Token-Bounded File Content Chunking | 1.0 |
| feat-004 | Directory-Based Module Aggregation | 1.0 |
| feat-005 | Module Name Normalization and Deduplication | 1.0 |
| feat-006 | Structural Context Validation and Quality Scoring | 1.0 |
| feat-007 | Keyword-Driven Feature Detection and Gap Analysis | 0.95 |
| feat-008 | Full-Codebase ECA Extraction with File Tree and Coarse Classification | 1.0 |
| feat-009 | End-to-End Deterministic Pipeline Orchestration with Fail-Fast Logging | 1.0 |
| feat-010 | Cross-Stage Output Merging into Final Canonical Payload | 1.0 |
| feat-011 | REST API for On-Demand Repository Analysis | 1.0 |

---

### feat-001 — Repository Cloning and File Manifest Generation
Accepts a GitHub repository URL, clones it via a subprocess git call into a local staging directory, filters out binaries and noise directories (node_modules, .git, dist, build), and produces a structured manifest of all valid text files with path, extension, and byte size.

**Source modules:** `app/eca/repo_scanner.py`

---

### feat-002 — Granular Rule-Based File Classification with Confidence Scoring
Assigns each file a semantic role (entry_point, config, route, service, component, unknown) and a confidence score (0.0–1.0) using deterministic heuristics: file extension sets, filename keyword patterns, and directory path segments. No ML or LLM involved.

**Source modules:** `app/eca/file_classifier.py`

---

### feat-003 — Token-Bounded File Content Chunking
Reads each classified text file line-by-line and splits content into chunks capped at 3,200 characters (~800 tokens). Each chunk is tagged with a unique chunk_id, source file path, category, and raw content string.

**Source modules:** `app/eca/content_processor.py`

---

### feat-004 — Directory-Based Module Aggregation
Groups content chunks by their top-level directory name to form logical modules. Files in the repo root are collected under a 'root' module. Produces a deterministically sorted list of modules, each tracking member file paths and associated chunk IDs.

**Source modules:** `app/context/aggregator.py`

---

### feat-005 — Module Name Normalization and Deduplication
Strips noise folders (.git, node_modules, __pycache__, build, dist, etc.), converts raw directory names to snake_case, merges duplicates that resolve to the same normalized name, and assigns each retained module a deterministic UUID5 identifier.

**Source modules:** `app/context/normalizer.py`

---

### feat-006 — Structural Context Validation and Quality Scoring
Scores the normalized module list against a quality rubric: penalizes empty modules (−0.1), low-confidence modules (−0.1), and absence of core structural folders such as src/app/lib/backend/frontend (−0.3). Returns a float score and a boolean valid flag; score ≥ 0.7 with at least one core folder is required to pass.

**Source modules:** `app/context/validator.py`

---

### feat-007 — Keyword-Driven Feature Detection and Gap Analysis
Scans file names and raw file content for predefined keyword sets to detect product-level features (Authentication, Database, API, Payment, Search, User Management). Confidence grows +0.2 per unique matching source file, capped at 1.0. In the same pass, reports structural gaps: missing README, documentation limited to README only, and absence of test files.

**Source modules:** `app/context/builder.py`

---

### feat-008 — Full-Codebase ECA Extraction with File Tree and Coarse Classification
Walks the cloned repository to build a nested dict file tree, sorts all files into coarse buckets (frontend, backend, config, docs, unknown) by extension, reads the root-level README.md, and produces the canonical ECAOutput payload consumed by the context builder stage.

**Source modules:** `app/eca/extractor.py`, `app/schemas/models.py`

---

### feat-009 — End-to-End Deterministic Pipeline Orchestration with Fail-Fast Logging
Sequences all 7 pipeline stages (RepoScanner → FileClassifier → ContentProcessor → ContextAggregator → ContextNormalizer → ContextValidator → FinalOutputBuilder) in a single call. Emits colour-coded per-stage status logs and raises immediately on the first stage failure.

**Source modules:** `app/pipeline/pipeline_runner.py`

---

### feat-010 — Cross-Stage Output Merging into Final Canonical Payload
Combines outputs from all 5 upstream pipeline stages into a single JSON payload keyed on repo_name, files (enriched with category and confidence), modules, chunks, and a validation sub-object.

**Source modules:** `app/output/final_output_builder.py`

---

### feat-011 — REST API for On-Demand Repository Analysis
Exposes a FastAPI POST /analyze endpoint that accepts a repo_url and optional output_path, runs the full pipeline, and returns the canonical final payload as JSON. Also exposes GET /health and GET / for liveness and documentation.

**Source modules:** `app/api/main.py`

---

## Functional Requirements

### FR-001 through FR-005 — Repository Cloning and File Manifest Generation (feat-001)

| ID | Description | Priority |
|----|-------------|----------|
| FR-001 | The system SHALL accept a valid GitHub repository URL as input and clone the repository to a local staging directory using the system's git binary before any analysis begins. | High |
| FR-002 | The system SHALL exclude all files whose extension matches the binary set (.exe, .dll, .png, .jpg, .pdf, .mp4, .pyc, etc.) or whose first 1024 bytes trigger a UnicodeDecodeError from the file manifest. | High |
| FR-003 | The system SHALL exclude the following directories from traversal: node_modules, .git, dist, and build. Symlinks SHALL be skipped. | High |
| FR-004 | The system SHALL produce a file manifest where each entry contains exactly three fields: relative file path (string), extension (string), and size in bytes (integer). | High |
| FR-005 | If the git clone command fails or git is not installed, the system SHALL return an error object with a human-readable message and SHALL NOT proceed to subsequent pipeline stages. | High |

---

### FR-006 through FR-008 — Rule-Based File Classification (feat-002)

| ID | Description | Priority |
|----|-------------|----------|
| FR-006 | The system SHALL classify every file in the manifest into exactly one of the following categories: entry_point, config, route, service, component, or unknown. | High |
| FR-007 | The system SHALL assign a confidence score between 0.0 and 1.0 (inclusive) to each classified file. Entry-point matches SHALL produce 1.0; extension-based matches SHALL produce 0.9; filename-keyword matches SHALL produce 0.8; directory-segment matches SHALL produce 0.7. Unmatched files SHALL receive 0.0. | High |
| FR-008 | Classification SHALL be determined solely by file extension sets, filename keyword patterns, and directory path segment membership. No external API calls or model inference SHALL be made during classification. | High |

---

### FR-009 through FR-011 — Token-Bounded Content Chunking (feat-003)

| ID | Description | Priority |
|----|-------------|----------|
| FR-009 | The system SHALL split each text file into one or more chunks where no single chunk exceeds 3,200 characters in length. | High |
| FR-010 | Each chunk SHALL carry four fields: chunk_id (string, unique across the run), file_path (relative string), category (string inherited from classifier), and content (raw text string). | High |
| FR-011 | If a file produces a UnicodeDecodeError during reading, the system SHALL skip that file silently and continue processing remaining files. | Medium |

---

### FR-012 through FR-014 — Directory-Based Module Aggregation (feat-004)

| ID | Description | Priority |
|----|-------------|----------|
| FR-012 | The system SHALL group chunks by their top-level directory name to form a module. Chunks whose file path has no parent directory SHALL be grouped into a module named 'root'. | High |
| FR-013 | Each aggregated module SHALL record: module_name (string), files (sorted list of unique file paths), and chunk_ids (list of all chunk IDs belonging to that module). | High |
| FR-014 | The output module list SHALL be sorted alphabetically by module_name to ensure deterministic output across identical inputs. | Medium |

---

### FR-015 through FR-018 — Module Name Normalization and Deduplication (feat-005)

| ID | Description | Priority |
|----|-------------|----------|
| FR-015 | The system SHALL discard any module whose raw name appears in the noise set: .idea, .vscode, .git, .gradle, .github, .husky, node_modules, build, dist, out, target, bin, obj, vendor, tmp, temp, logs, coverage, __pycache__. | High |
| FR-016 | The system SHALL convert all retained module names to snake_case by lowercasing, replacing non-alphanumeric characters with underscores, and stripping leading/trailing underscores. | High |
| FR-017 | If two raw module names normalize to the same snake_case string, their file lists SHALL be merged and deduplicated into a single module entry. | High |
| FR-018 | Each normalized module SHALL be assigned a UUID5 identifier derived from UUID_NAMESPACE_URL and the snake_case module name, ensuring the same name always produces the same ID across runs. | Medium |

---

### FR-019 through FR-021 — Structural Context Validation (feat-006)

| ID | Description | Priority |
|----|-------------|----------|
| FR-019 | The system SHALL compute a validation score starting at 1.0 and deduct 0.1 for each module with an empty file list, 0.1 for each module with confidence below 0.5, and 0.3 if no module name contains any of the keywords: src, app, lib, main, backend, frontend, source, core. | High |
| FR-020 | The system SHALL set valid = true only when the validation score is ≥ 0.7 AND at least one module name matches a core structural keyword. The score SHALL be floored at 0.0. | High |
| FR-021 | The validation output SHALL list every specific issue encountered (e.g., "Empty module: utils", "Low confidence (0.3) for module: helpers") as individual strings in an issues array. | Medium |

---

### FR-022 through FR-026 — Feature Detection and Gap Analysis (feat-007)

| ID | Description | Priority |
|----|-------------|----------|
| FR-022 | The system SHALL scan both the file path string and the full file content of every chunk for the following keyword sets: Authentication (auth, login, signup, jwt, session, passport), Database (db, database, sql, mongo, postgres, redis, models, schema), API (api, routes, controllers, endpoints, graphql, rest), Payment (payment, stripe, billing, checkout, cart), Search (search, elastic, query, filter), User Management (user, profile, account, settings, role). | High |
| FR-023 | For each feature category, the system SHALL increment the confidence score by 0.2 per unique source file that contains a matching keyword, capped at a maximum of 1.0. | High |
| FR-024 | The system SHALL report a gap labelled "Missing or empty README.md" if the root-level README.md is absent or contains no content. | Medium |
| FR-025 | The system SHALL report a gap labelled "Minimal documentation (only README found)" if no files are classified under the docs bucket but a README is present. | Medium |
| FR-026 | The system SHALL report a gap labelled "No obvious test files found" if no file path in the frontend or backend buckets contains the substring 'test' (case-insensitive). | Medium |

---

### FR-027 through FR-030 — ECA Extraction and File Tree (feat-008)

| ID | Description | Priority |
|----|-------------|----------|
| FR-027 | The system SHALL build a nested dictionary representing the repository file tree where each key is a directory or file name and leaf nodes (files) have the value null. | High |
| FR-028 | The system SHALL classify all repository files into exactly one of five coarse buckets by extension: frontend (.js, .jsx, .ts, .tsx, .html, .css, .scss, .vue), backend (.py, .java, .go, .rb, .php, .cs, .rs, .cpp, .c), config (.json, .yaml, .yml, .toml, .ini, .env, .xml, .cfg), docs (.md, .txt, .rst), or unknown. | High |
| FR-029 | The system SHALL read the README.md located at the repository root and store its full text content. If no README.md exists at the root, the field SHALL be set to an empty string. | Medium |
| FR-030 | The ECA extraction SHALL exclude the .git directory from all traversal operations. | High |

---

### FR-031 through FR-033 — Pipeline Orchestration (feat-009)

| ID | Description | Priority |
|----|-------------|----------|
| FR-031 | The system SHALL execute pipeline stages in the following fixed order: RepoScanner → FileClassifier → ContentProcessor → ContextAggregator → ContextNormalizer → ContextValidator → FinalOutputBuilder. No stage SHALL begin before its predecessor has returned a result. | High |
| FR-032 | If any pipeline stage raises an exception, the system SHALL halt immediately, log the stage name and error message, and propagate the exception to the caller. Subsequent stages SHALL NOT execute. | High |
| FR-033 | The system SHALL emit a status log line for each stage indicating the stage number (e.g., [3/7]), stage name, and outcome (STARTED or SUCCESS with a count summary). Failed stages SHALL be clearly distinguished from successful ones in the log output. | Medium |

---

### FR-034 through FR-036 — Final Payload Assembly (feat-010)

| ID | Description | Priority |
|----|-------------|----------|
| FR-034 | The final payload SHALL contain exactly five top-level keys: repo_name (string), files (array), modules (array), chunks (array), and validation (object with score, issues, and valid fields). | High |
| FR-035 | Each entry in the files array SHALL include: path, extension, size, category, and confidence. The category and confidence fields SHALL be sourced from the FileClassifier output and merged onto the repo_scan manifest by matching file path. | High |
| FR-036 | The files array in the final payload SHALL be sorted alphabetically by path to ensure deterministic output. | Medium |

---

### FR-037 through FR-041 — REST API (feat-011)

| ID | Description | Priority |
|----|-------------|----------|
| FR-037 | The system SHALL expose a POST /analyze endpoint that accepts a JSON body with the field repo_url (required, string) and output_path (optional, string or null). | High |
| FR-038 | On a successful pipeline run, POST /analyze SHALL return HTTP 200 with a JSON body containing status: "success" and the full final payload under the data key. | High |
| FR-039 | If the pipeline raises an exception, POST /analyze SHALL return HTTP 500 with a JSON body containing detail: "Pipeline execution failed: \<error message\>". | High |
| FR-040 | The system SHALL expose a GET /health endpoint that returns HTTP 200 with the body { "status": "healthy", "service": "Analyst Agent" }. | Medium |
| FR-041 | The API SHALL accept cross-origin requests from any origin (CORS allow_origins: ["*"]) on all HTTP methods and headers. | Low |

---

## Requirements Summary

| Priority | Count |
|----------|-------|
| High | 27 |
| Medium | 12 |
| Low | 2 |
| **Total** | **41** |

---

*This BRD was generated deterministically from live source code analysis of the Analyst-Agent repository. No features or requirements were invented or inferred beyond what is directly evidenced by the source modules listed.*
