---
name: data-platform-analysis
version: "1.0"
description: >-
  Analysis pack for data engineering and ETL/ELT platform repositories.
  Activate when data orchestration tools (Airflow, dbt, Spark, Kafka,
  Flink) or data warehouse dependencies (BigQuery, Snowflake, Redshift)
  are detected.
  DO NOT activate for: ML notebooks without pipeline orchestration,
  simple CRUD apps with basic database usage.

detection_signals:
  evidence_flags: [has_database]
  dependency_keywords: [airflow, apache-airflow, dbt, dbt-core, pyspark, apache-spark, kafka, apache-kafka, flink, dagster, prefect, luigi, celery, bigquery, snowflake, redshift, duckdb, clickhouse, delta-lake, iceberg]
  file_patterns: ["**/dags/**", "**/dbt_project.yml", "**/models/**/*.sql", "**/pipelines/**", "**/etl/**", "**/airflow/**", "**/spark/**"]
  confidence_threshold: 0.5

nfr_emphasis: [data_freshness_sla, pipeline_throughput, data_quality, fault_tolerance, data_lineage]
memory_tags: [data_pipeline, etl, orchestration, data_warehouse, streaming, batch]
brd_section_notes:
  section_5: "Focus on data pipeline stages: ingest, transform, load, quality checks, scheduling"
  section_6: "Include data freshness SLAs, pipeline uptime targets, and retry policies"
  section_7: "Emphasise data schemas, source system contracts, and data quality dimensions"
  section_8: "Document orchestration tools, compute infrastructure, and storage tiers"
---

# Data Platform Analysis Skill Pack

## Overview

This skill pack extracts data pipeline DAGs, transformation stages, scheduling
patterns, data source/sink definitions, and quality check mechanisms from
data engineering repositories.

## When This Skill Activates

- Dependencies include orchestration tools: Airflow, dbt, Dagster, Prefect
- Dependencies include processing engines: Spark, Kafka, Flink
- File tree contains `dags/`, `models/*.sql`, `pipelines/`, `etl/` directories
- `evidence.has_database == True` (combined with orchestrator deps)

## Extraction Scripts

### Script 1: Pipeline/DAG Detection

```bash
python scripts/pipeline_extractor.py <repo_dir> <output.json> dags
```

Detects Airflow DAGs, dbt models, Dagster pipelines, and custom ETL scripts.

### Script 2: Data Source/Sink Detection

```bash
python scripts/pipeline_extractor.py <repo_dir> <output.json> sources
```

Identifies database connections, file sources, API sources, and output targets.

### Script 3: Data Quality Checks

```bash
python scripts/pipeline_extractor.py <repo_dir> <output.json> quality
```

Detects data validation frameworks (Great Expectations, dbt tests, custom assertions).

## Common Mistakes

- Do NOT count database migration files as data pipeline stages
- Do NOT assume real-time processing from the presence of Kafka alone
- dbt test files are quality checks, not business features
