"""
pipeline_extractor.py — Data Platform Skill Pack Extraction Script
--------------------------------------------------------------------
Extracts data pipeline DAGs, data sources/sinks, and quality checks
from data engineering repositories.

Usage:
    python scripts/pipeline_extractor.py <repo_dir> <output_file> <subcommand>

Subcommands:
    dags    — Detect Airflow DAGs, dbt models, Dagster pipelines
    sources — Detect data source/sink connections
    quality — Detect data quality check patterns
    extract — Run all subcommands and merge

Uses ONLY stdlib — no pip installs required.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Any


# ---------------------------------------------------------------------------
# DAG / Pipeline Patterns
# ---------------------------------------------------------------------------

# Airflow DAG definitions
_AIRFLOW_DAG_RE = re.compile(
    r"""DAG\s*\(\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
_AIRFLOW_TASK_RE = re.compile(
    r"""(\w+Operator|PythonOperator|BashOperator|SparkSubmitOperator|BigQueryOperator|PostgresOperator)\s*\(""",
    re.IGNORECASE,
)

# dbt model SQL files
_DBT_REF_RE = re.compile(r"\{\{\s*ref\s*\(\s*['\"](\w+)['\"]\s*\)\s*\}\}")
_DBT_SOURCE_RE = re.compile(r"\{\{\s*source\s*\(\s*['\"](\w+)['\"]")

# Dagster
_DAGSTER_RE = re.compile(r"@(?:asset|op|job|graph|schedule|sensor)\b", re.IGNORECASE)

# Prefect
_PREFECT_RE = re.compile(r"@(?:flow|task)\b", re.IGNORECASE)

# Luigi
_LUIGI_RE = re.compile(r"class\s+(\w+)\s*\(.*(?:luigi\.Task|Task)\)", re.IGNORECASE)

# Spark
_SPARK_RE = re.compile(r"SparkSession|spark\.read|spark\.sql|DataFrame|rdd\.", re.IGNORECASE)

# Kafka
_KAFKA_RE = re.compile(r"KafkaProducer|KafkaConsumer|kafka\.consumer|kafka\.producer|bootstrap\.servers", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Data Source/Sink Patterns
# ---------------------------------------------------------------------------

_SOURCE_PATTERNS = {
    "postgresql": re.compile(r"postgresql://|psycopg2|pg_connection|PostgresHook", re.IGNORECASE),
    "mysql": re.compile(r"mysql://|pymysql|mysql\.connector|MySqlHook", re.IGNORECASE),
    "bigquery": re.compile(r"bigquery|BigQueryHook|google\.cloud\.bigquery", re.IGNORECASE),
    "snowflake": re.compile(r"snowflake\.connector|SnowflakeHook|snowflake://", re.IGNORECASE),
    "redshift": re.compile(r"redshift|RedshiftHook|redshift-connector", re.IGNORECASE),
    "s3": re.compile(r"boto3.*s3|S3Hook|s3://|aws_s3", re.IGNORECASE),
    "gcs": re.compile(r"google\.cloud\.storage|GCSHook|gs://", re.IGNORECASE),
    "mongodb": re.compile(r"pymongo|MongoClient|mongodb://", re.IGNORECASE),
    "elasticsearch": re.compile(r"elasticsearch|Elasticsearch\(|es_client", re.IGNORECASE),
    "redis": re.compile(r"redis\.Redis|aioredis|RedisHook", re.IGNORECASE),
    "csv_file": re.compile(r"pd\.read_csv|\.csv['\"]|csv\.reader|csv\.writer", re.IGNORECASE),
    "parquet": re.compile(r"\.parquet|read_parquet|to_parquet|pyarrow", re.IGNORECASE),
}


# ---------------------------------------------------------------------------
# Data Quality Patterns
# ---------------------------------------------------------------------------

_QUALITY_PATTERNS = {
    "great_expectations": re.compile(r"great_expectations|expect_column|ExpectationSuite|ge\.dataset", re.IGNORECASE),
    "dbt_tests": re.compile(r"unique|not_null|accepted_values|relationships", re.IGNORECASE),
    "custom_assertion": re.compile(r"assert\s+len|assert\s+\w+\s*[><=!]=|data_quality_check|validate_schema", re.IGNORECASE),
    "schema_validation": re.compile(r"pydantic|marshmallow|cerberus|jsonschema|voluptuous", re.IGNORECASE),
    "null_check": re.compile(r"isnull\(\)\.sum|notnull|dropna|fillna|missing_values", re.IGNORECASE),
}


# ---------------------------------------------------------------------------
# File Walker
# ---------------------------------------------------------------------------

_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", "venv", ".venv", "vendor",
    "dist", "build", ".next", "target", ".gradle",
}

_DATA_EXTS = {".py", ".sql", ".yml", ".yaml", ".toml", ".cfg"}


def _walk_data_files(repo_dir: str) -> List[tuple[str, str]]:
    """Walk repo for data-engineering relevant files."""
    results = []
    root = Path(repo_dir)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        rel_dir = Path(dirpath).relative_to(root)
        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext not in _DATA_EXTS:
                continue
            fpath = Path(dirpath) / fname
            if fpath.stat().st_size > 500_000:
                continue
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                results.append((str(rel_dir / fname), content))
            except (OSError, UnicodeDecodeError):
                continue
    return results


# ---------------------------------------------------------------------------
# Subcommand: dags
# ---------------------------------------------------------------------------

def cmd_dags(repo_dir: str) -> Dict[str, Any]:
    """Detect data pipeline definitions (DAGs, dbt models, etc.)."""
    pipelines: List[Dict[str, Any]] = []
    orchestrators: set = set()

    for rel_path, content in _walk_data_files(repo_dir):
        # Airflow DAGs
        for m in _AIRFLOW_DAG_RE.finditer(content):
            pipelines.append({"name": m.group(1), "type": "airflow_dag", "source_file": rel_path})
            orchestrators.add("airflow")

        # Airflow tasks
        if _AIRFLOW_TASK_RE.search(content):
            orchestrators.add("airflow")

        # dbt models (SQL files with ref/source)
        if _DBT_REF_RE.search(content) or _DBT_SOURCE_RE.search(content):
            model_name = Path(rel_path).stem
            pipelines.append({"name": model_name, "type": "dbt_model", "source_file": rel_path})
            orchestrators.add("dbt")

        # Dagster
        if _DAGSTER_RE.search(content):
            orchestrators.add("dagster")
            pipelines.append({"name": Path(rel_path).stem, "type": "dagster_asset", "source_file": rel_path})

        # Prefect
        if _PREFECT_RE.search(content):
            orchestrators.add("prefect")
            pipelines.append({"name": Path(rel_path).stem, "type": "prefect_flow", "source_file": rel_path})

        # Luigi
        for m in _LUIGI_RE.finditer(content):
            pipelines.append({"name": m.group(1), "type": "luigi_task", "source_file": rel_path})
            orchestrators.add("luigi")

        # Spark jobs
        if _SPARK_RE.search(content):
            orchestrators.add("spark")

        # Kafka
        if _KAFKA_RE.search(content):
            orchestrators.add("kafka")

    # Dedup
    seen = set()
    deduped = []
    for p in pipelines:
        key = (p["name"], p["type"])
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    features = []
    if deduped:
        features.append({
            "name": "data_pipeline_orchestration",
            "description": f"Data pipeline with {len(deduped)} pipeline component(s) using {', '.join(sorted(orchestrators))}",
            "confidence": 0.9,
            "source_modules": list(set(p["source_file"] for p in deduped))[:5],
        })

    for orch in orchestrators:
        features.append({
            "name": f"{orch}_integration",
            "description": f"Data processing integration with {orch.title()}",
            "confidence": 0.85,
            "source_modules": [],
        })

    return {
        "pipelines": deduped,
        "orchestrators": sorted(orchestrators),
        "total_pipelines": len(deduped),
        "features": features,
    }


# ---------------------------------------------------------------------------
# Subcommand: sources
# ---------------------------------------------------------------------------

def cmd_sources(repo_dir: str) -> Dict[str, Any]:
    """Detect data source and sink connections."""
    sources_found: Dict[str, List[str]] = {}

    for rel_path, content in _walk_data_files(repo_dir):
        for source_name, pattern in _SOURCE_PATTERNS.items():
            if pattern.search(content):
                sources_found.setdefault(source_name, []).append(rel_path)

    features = []
    if sources_found:
        src_names = ", ".join(sorted(sources_found.keys()))
        features.append({
            "name": "data_source_integration",
            "description": f"Data pipeline connects to {len(sources_found)} source/sink type(s): {src_names}",
            "confidence": 0.85,
            "source_modules": [],
        })

    return {
        "data_sources": {k: v[:3] for k, v in sources_found.items()},
        "source_types": sorted(sources_found.keys()),
        "features": features,
    }


# ---------------------------------------------------------------------------
# Subcommand: quality
# ---------------------------------------------------------------------------

def cmd_quality(repo_dir: str) -> Dict[str, Any]:
    """Detect data quality check mechanisms."""
    quality_found: Dict[str, List[str]] = {}

    for rel_path, content in _walk_data_files(repo_dir):
        for qtype, pattern in _QUALITY_PATTERNS.items():
            if pattern.search(content):
                quality_found.setdefault(qtype, []).append(rel_path)

    features = []
    if quality_found:
        features.append({
            "name": "data_quality_framework",
            "description": f"Data quality checks using: {', '.join(sorted(quality_found.keys()))}",
            "confidence": 0.8,
            "source_modules": [],
        })

    return {
        "quality_checks": {k: v[:3] for k, v in quality_found.items()},
        "quality_types": sorted(quality_found.keys()),
        "features": features,
    }


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Data Platform Skill Pack — Extract DAGs, sources, and quality checks"
    )
    parser.add_argument("repo_dir", help="Path to cloned repository root")
    parser.add_argument("output_file", help="Path to write JSON output")
    parser.add_argument(
        "subcommand",
        choices=["dags", "sources", "quality", "extract"],
        help="Extraction subcommand",
    )
    args = parser.parse_args()

    if not Path(args.repo_dir).is_dir():
        print(f"Error: {args.repo_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    handlers = {
        "dags": cmd_dags,
        "sources": cmd_sources,
        "quality": cmd_quality,
        "extract": lambda d: {
            **cmd_dags(d),
            "sources": cmd_sources(d),
            "quality": cmd_quality(d),
        },
    }

    result = handlers[args.subcommand](args.repo_dir)
    out = Path(args.output_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"Success! {args.subcommand} → {out} ({len(result.get('features', []))} features)")


if __name__ == "__main__":
    main()
