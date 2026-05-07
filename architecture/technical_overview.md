
# Analyst-Agent Technical Overview

This document provides a comprehensive overview of the Analyst-Agent's architecture, the deterministic data extraction pipeline, and the core functions of its components.

## A.N.T. 3-Layer Architecture

The Analyst-Agent follows the **A.N.T. (Architecture, Navigation, Tools)** 3-Layer Architecture to ensure reliability, maintainability, and deterministic behavior.

### Layer 1: Architecture (`architecture/`)
- **Role**: The "source of truth" for technical standards and procedures.
- **Components**: Contains Standard Operating Procedures (SOPs) and documentation (like this file).
- **Invariant**: If logic changes, the SOP must be updated before the code.

### Layer 2: Navigation (`app/api/`, `app/pipeline/`)
- **Role**: The reasoning and coordination layer.
- **Components**:
    - **API**: Handles external requests and translates them into pipeline tasks.
    - **Pipeline Runner**: Orchestrates the flow of data between deterministic tools.
- **Constraint**: This layer manages flow but does not perform complex data transformations directly.

### Layer 3: Tools (`app/eca/`, `app/context/`)
- **Role**: The deterministic execution layer.
- **Components**: Atomic, testable Python scripts that perform specific transformations (Extraction, Classification, Aggregation).
- **Constraint**: This layer is strictly **deterministic** and does not use LLMs for its core logic.

---

## Deterministic Extraction Pipeline

The pipeline transforms a raw GitHub repository into a structured Knowledge Context in three main stages:

### 1. Ingest
- **Module**: `app/pipeline/ingest.py`
- **Action**: Clones the target repository into a temporary directory (`.tmp/repo/`).
- **Goal**: Provide a local copy of the codebase for analysis.

### 2. ECA Extraction (Extraction, Classification, Analysis)
- **Module**: `app/eca/extractor.py`
- **Goal**: Produce a structured JSON payload (`eca_output.json`) representing the raw state of the repository.
- **Sub-Components**:
    - **Repo Scanner (`repo_scanner.py`)**: Traverses the directory to build a hierarchical file tree.
    - **File Classifier (`file_classifier.py`)**: Categorizes files into `frontend`, `backend`, `config`, `docs`, or `unknown` based on extensions and path patterns.
    - **Content Processor (`content_processor.py`)**: Reads and chunks text files to prepare content for indexing/analysis.

### 3. Context Building
- **Module**: `app/context/builder.py`
- **Goal**: Transform raw ECA output into high-level project context (`context_output.json`).
- **Actions**:
    - **Feature Mapping**: Scans file names and content for predefined keywords (e.g., "auth" -> Authentication) to identify system capabilities.
    - **Module Detection**: Aggregates files into logical modules (e.g., "API", "Database").
    - **Gap Analysis**: Identifies missing critical components like READMEs or tests.

---

## Core File Functions Reference

| File | Primary Function | Key Output |
| :--- | :--- | :--- |
| `extractor.py` | Orchestrates the ECA (Extraction, Classification, Analysis) phase. | `ECAOutput` JSON |
| `repo_scanner.py` | Recursively walks the directory to build a structural map. | File Tree |
| `file_classifier.py` | Assigns roles to files based on deterministic rules (extensions). | Classified File Lists |
| `content_processor.py` | Sanitizes and chunks file contents for processing. | Chunks/Snippets |
| `builder.py` | Maps raw code artifacts to high-level features and identifies gaps. | `NormalizedContext` JSON |
| `pipeline_runner.py` | Orchestrates the entire end-to-end flow from URL to Context. | Final Payload |

---

## Data Schemas

The pipeline relies on strictly defined Pydantic schemas (found in `app/schemas/models.py`):

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
  "features": [ { "name": "string", "confidence": 0.9, "sources": [] } ],
  "modules": ["string"],
  "gaps": ["string"]
}
```
