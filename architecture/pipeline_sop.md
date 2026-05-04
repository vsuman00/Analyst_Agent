# Deterministic Pipeline SOP

## Overview
This document outlines the standard operating procedure for the deterministic data pipeline of the Analyst Agent. It covers the full flow from ingesting a GitHub repository through to producing a structured MinimalBRD — all without LLM inference.

## Process Flow

### Core Pipeline (Stages 1–7, `app/pipeline/pipeline_runner.py`)

| Stage | Module | Input | Output |
|-------|--------|-------|--------|
| 1 | RepoScanner | repo_url | repo_scan.json |
| 2 | FileClassifier | repo_scan.json | classified_files.json |
| 3 | ContentProcessor | classified_files.json | chunks_output.json |
| 4 | ContextAggregator | chunks_output.json | aggregated_context.json |
| 5 | ContextNormalizer | aggregated_context.json | normalized_context.json |
| 6 | ContextValidator | normalized_context.json | validation_result.json |
| 7 | FinalOutputBuilder | all above | **final_payload.json** |

### Conversion Layer (Stage 8, `app/analysis/payload_converter.py`)

**Input:** `final_payload.json`
```json
{
  "repo_name": "string",
  "files": [...],
  "modules": [...],
  "chunks": [...],
  "validation": { "score": float, "issues": [...], "valid": bool }
}
```

**Sub-stages (all rule-based, no LLM):**

1. `extract_features(payload)` — Derives one `AnalysisFeature` per normalized module + a meta-feature from validation score. Confidence is inherited directly from `modules[].confidence`.
2. `derive_requirements(features)` — Produces one SHALL-style `Requirement` per feature. Priority is derived from feature category via `PRIORITY_MAP`; low-confidence features are downgraded.
3. `build_brd(payload)` — Assembles a `MinimalBRD` from the three sub-outputs.

**Output:** `MinimalBRD` (see `app/schemas/models.py`)
```json
{
  "repo_name": "string",
  "summary": "string",
  "validation_score": float,
  "validation_passed": bool,
  "features": [{ "id", "name", "confidence", "sources", "category" }],
  "requirements": [{ "id", "feature_id", "description", "priority", "source_modules" }],
  "gaps": ["string"],
  "modules_detected": ["string"]
}
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe |
| POST | `/analyze` | Run pipeline only; returns `final_payload` |
| POST | `/convert` | Convert pre-computed payload → `MinimalBRD` |
| POST | `/analyze-and-convert` | Pipeline + conversion in one call |

## Error Handling & Reliability
- Any stage failure raises immediately; subsequent stages do NOT execute.
- All temporary operations MUST happen in `runtime/outputs/`.
- Conversion stage failures do NOT affect pipeline output; they are caught independently at the API layer.
- Confidence values are NEVER inflated beyond what the source data provides.

