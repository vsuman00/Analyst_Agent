"""
feature_extraction_agent.py — Layer 3 Tool
-------------------------------------------
FeatureExtractionAgent

Inputs:
  - normalized_modules : List of normalized module dicts
      { "id": str, "name": str, "files": [str], "confidence": float }
  - chunks             : List of chunk dicts (content used as summarized context)
      { "chunk_id": str, "file_path": str, "category": str, "content": str }

Output (strict JSON):
  {
    "features": [
      {
        "id": str,
        "name": str,
        "description": str,
        "source_modules": [str],
        "confidence": float
      }
    ]
  }

Extraction logic:
  1. KEYWORD SCAN — each chunk's file_path + first 512 chars of content are
     scanned against FEATURE_REGISTRY keyword sets.
  2. MODULE ANCHORING — every candidate feature is cross-referenced against
     normalized_modules. A feature is only emitted if ≥1 source module can
     be resolved. Unanchored features are silently dropped.
  3. CONFIDENCE SCORING
       - keyword found in module name              → base 0.9
       - keyword found in file path only           → base 0.75
       - keyword found in content only             → base 0.55
       - each additional unique source file        → +0.05 (cap 1.0)
       - below 0.4 after all scoring → dropped (noise guard)
  4. DEDUPLICATION — features resolving to the same (name, frozenset(source_modules))
     are merged; their confidences are max-pooled.
  5. DESCRIPTION GENERATION — concise, technical, template-driven. No business language.

Strict rules enforced:
  - No feature is emitted without ≥1 resolved source_module
  - No generic/subjective feature names (UI, UX, performance, scalability, etc.)
  - Descriptions are ≤ 2 sentences and factual
  - Output is sorted by confidence desc, then name asc

Usage (CLI):
  python -m app.analysis.feature_extraction_agent \
    --modules runtime/outputs/normalized_context.json \
    --chunks  runtime/outputs/chunks_output.json \
    [--out    runtime/outputs/extracted_features.json]
"""

from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple

from app.schemas.models import ExtractedFeature, FeatureExtractionResult

# ---------------------------------------------------------------------------
# Feature Registry
# Each entry: feature_name → { keywords, description_template }
# description_template receives:
#   {module_list}  — comma-joined source module names
#   {file_count}   — number of source files
# ---------------------------------------------------------------------------

FEATURE_REGISTRY: Dict[str, Dict] = {
    "Token-Based Authentication": {
        "keywords": {"auth", "login", "signup", "jwt", "session", "passport", "token", "bearer"},
        "description": (
            "Implements token-based authentication (e.g., JWT/session) "
            "across {module_list} ({file_count} file(s)). "
            "Handles credential validation and session lifecycle."
        ),
    },
    "Database Access Layer": {
        "keywords": {"db", "database", "sql", "mongo", "postgres", "redis", "repository", "schema", "datasource", "jdbc"},
        "description": (
            "Provides a structured database access layer in {module_list} ({file_count} file(s)). "
            "Covers schema definitions, repository interfaces, and query execution."
        ),
    },
    "REST API Routing": {
        "keywords": {"api", "routes", "controller", "endpoint", "handler", "rest", "graphql", "mapping", "requestmapping"},
        "description": (
            "Defines REST or GraphQL API routes and request handlers in {module_list} ({file_count} file(s)). "
            "Maps HTTP methods to service-layer invocations."
        ),
    },
    "Domain Service Layer": {
        "keywords": {"service", "usecase", "domain", "business", "logic", "application"},
        "description": (
            "Encapsulates domain/business logic as service classes in {module_list} ({file_count} file(s)). "
            "Coordinates between repository and handler layers."
        ),
    },
    "Domain Entity Modelling": {
        "keywords": {"entity", "model", "record", "dto", "pojo", "dataclass", "struct"},
        "description": (
            "Declares domain entity models and data-transfer objects in {module_list} ({file_count} file(s)). "
            "Defines the core data structures exchanged between layers."
        ),
    },
    "User Management": {
        "keywords": {"user", "profile", "account", "role", "permission", "authority", "member"},
        "description": (
            "Manages user records, roles, and authority assignments in {module_list} ({file_count} file(s)). "
            "Includes user repository and authority/permission structures."
        ),
    },
    "Notification System": {
        "keywords": {"notification", "notify", "alert", "push", "firebase", "fcm", "webhook"},
        "description": (
            "Implements push or event-based notifications in {module_list} ({file_count} file(s)). "
            "Covers notification entity, repository, and delivery service."
        ),
    },
    "Content/Feed Management": {
        "keywords": {"tweet", "post", "feed", "content", "message", "item", "comment"},
        "description": (
            "Handles creation, retrieval, and management of user-generated content in {module_list} ({file_count} file(s)). "
            "Covers content entities, repositories, and service operations."
        ),
    },
    "Social Graph (Follow/Friend)": {
        "keywords": {"friend", "follow", "follower", "friend", "social", "relation", "connection"},
        "description": (
            "Models social relationships (follows/friendships) in {module_list} ({file_count} file(s)). "
            "Manages bidirectional links between user entities."
        ),
    },
    "Search and Query Filtering": {
        "keywords": {"search", "elastic", "query", "filter", "full-text", "index", "lucene"},
        "description": (
            "Provides search and structured query filtering in {module_list} ({file_count} file(s)). "
            "Supports keyword lookup, field filters, and optional full-text indexing."
        ),
    },
    "Payment Processing": {
        "keywords": {"payment", "stripe", "billing", "checkout", "cart", "invoice", "transaction"},
        "description": (
            "Integrates payment processing in {module_list} ({file_count} file(s)). "
            "Handles charge initiation, billing records, and transaction state."
        ),
    },
    "Container Orchestration Config": {
        "keywords": {"docker", "dockerfile", "compose", "kubernetes", "k8s", "helm", "kubectl", "deploy"},
        "description": (
            "Declares container build and orchestration configuration in {module_list} ({file_count} file(s)). "
            "Covers Docker image builds, Compose services, and Kubernetes deployment manifests."
        ),
    },
    "CI/CD Pipeline Config": {
        "keywords": {"ci", "cd", "pipeline", "github-actions", "cloudbuild", "workflow", "jenkins", "travis", "circleci"},
        "description": (
            "Defines continuous integration and deployment pipelines in {module_list} ({file_count} file(s)). "
            "Automates build, test, and deployment steps."
        ),
    },
    "gRPC / Protocol Buffer Interface": {
        "keywords": {"proto", "grpc", "protobuf", ".proto", "stub", "rpc"},
        "description": (
            "Declares gRPC service contracts via Protocol Buffer definitions in {module_list} ({file_count} file(s)). "
            "Used for typed, high-performance inter-service communication."
        ),
    },
    "Secret / Credential Management": {
        "keywords": {"secret", "credential", "kubesec", "vault", "encrypt", "decrypt", "env"},
        "description": (
            "Manages sensitive credentials and secrets in {module_list} ({file_count} file(s)). "
            "Includes encrypted secret files and environment variable configuration."
        ),
    },
    "Automated Test Suite": {
        "keywords": {"test", "spec", "assert", "unittest", "testcase", "junit", "mockito", "pytest"},
        "description": (
            "Contains automated tests in {module_list} ({file_count} file(s)). "
            "Validates service-layer behaviour and integration contracts."
        ),
    },
}

# Generic/subjective names that are blocked regardless of keyword hits
_BLOCKED_NAMES: Set[str] = {
    "user-friendly ui", "performance", "scalability", "usability",
    "reliability", "maintainability", "ui", "ux", "frontend ui",
    "backend services", "configuration management",
}

# Module-name fragments used to resolve normalized module names
# Maps lower-case path fragment → normalized module name hint
_MODULE_FRAGMENT_HINTS: Dict[str, str] = {}  # populated dynamically at runtime

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _content_summary(content: str, max_chars: int = 512) -> str:
    """Return the first max_chars of chunk content — the 'summarized context'."""
    return content[:max_chars]


def _keywords_in_text(text: str, keywords: Set[str]) -> Set[str]:
    """Return the subset of keywords found as whole-word substrings in text."""
    lower = text.lower()
    return {kw for kw in keywords if kw in lower}


def _resolve_module(file_path: str, module_index: Dict[str, Dict]) -> str | None:
    """
    Map a file_path to a normalized module name.
    Strategy: top-level directory of the path → look up in module_index.
    Falls back to 'root' if file is at repo root.
    Returns None if no match found (feature must not count this file).
    """
    parts = file_path.replace("\\", "/").split("/")
    top_dir = parts[0] if len(parts) > 1 else "root"
    return top_dir if top_dir in module_index else None


def _build_module_index(normalized_modules: List[Dict]) -> Dict[str, Dict]:
    """Build a fast lookup dict: module_name → module record."""
    return {m["name"]: m for m in normalized_modules}


def _make_description(template: str, source_modules: List[str], file_count: int) -> str:
    module_list = ", ".join(sorted(source_modules)) if source_modules else "unknown"
    return template.format(module_list=module_list, file_count=file_count)


# ---------------------------------------------------------------------------
# Core extraction logic
# ---------------------------------------------------------------------------

def _scan_chunks(
    chunks: List[Dict],
    module_index: Dict[str, Dict],
) -> Dict[str, Dict]:
    """
    Scan all chunks and accumulate evidence per feature.

    Returns a dict: feature_name → {
        "hits_by_source": { module_name: { file_path: { "path_match": bool, "content_match": bool } } }
    }
    """
    evidence: Dict[str, Dict] = {}

    for chunk in chunks:
        file_path: str = chunk.get("file_path", "")
        content_summary: str = _content_summary(chunk.get("content", ""))

        resolved_module = _resolve_module(file_path, module_index)
        if resolved_module is None:
            # File doesn't belong to any recognized module — skip
            continue

        path_lower = file_path.lower()

        for feat_name, spec in FEATURE_REGISTRY.items():
            kw_set: Set[str] = spec["keywords"]

            path_hits = _keywords_in_text(path_lower, kw_set)
            content_hits = _keywords_in_text(content_summary, kw_set)

            if not (path_hits or content_hits):
                continue

            if feat_name not in evidence:
                evidence[feat_name] = {}

            mod_evidence = evidence[feat_name].setdefault(resolved_module, {})
            file_record = mod_evidence.setdefault(file_path, {"path_match": False, "content_match": False})
            file_record["path_match"] = file_record["path_match"] or bool(path_hits)
            file_record["content_match"] = file_record["content_match"] or bool(content_hits)

    return evidence


def _score_feature(
    feat_name: str,
    module_evidence: Dict[str, Dict],  # module_name → { file_path → record }
    module_index: Dict[str, Dict],
) -> float:
    """
    Compute confidence score for a feature candidate.

    Base score:
      - keyword in module name (e.g., 'database' module name contains 'db') → 0.9
      - keyword in at least one file_path                                   → 0.75
      - keyword only in content                                             → 0.55

    Bonus: +0.05 per additional unique source file (cap at 1.0).
    """
    kw_set = FEATURE_REGISTRY[feat_name]["keywords"]
    module_names = list(module_evidence.keys())

    # Determine base score
    module_name_hit = any(
        any(kw in mod.lower() for kw in kw_set)
        for mod in module_names
    )

    all_records = [
        rec
        for mod_files in module_evidence.values()
        for rec in mod_files.values()
    ]

    path_hit = any(r["path_match"] for r in all_records)
    content_hit = any(r["content_match"] for r in all_records)

    if module_name_hit:
        base = 0.9
    elif path_hit:
        base = 0.75
    elif content_hit:
        base = 0.55
    else:
        base = 0.4

    # Bonus for additional unique files
    unique_files = sum(len(files) for files in module_evidence.values())
    bonus = min(0.1, (unique_files - 1) * 0.05)  # cap bonus at 0.1

    return round(min(1.0, base + bonus), 2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_features(
    normalized_modules: List[Dict],
    chunks: List[Dict],
) -> FeatureExtractionResult:
    """
    Extract real, module-anchored features from normalized_modules + chunks.

    Parameters
    ----------
    normalized_modules : list of module dicts
        { "id": str, "name": str, "files": [str], "confidence": float }
    chunks : list of chunk dicts
        { "chunk_id": str, "file_path": str, "category": str, "content": str }

    Returns
    -------
    FeatureExtractionResult
        { "features": [ ExtractedFeature, ... ] }
    """
    module_index = _build_module_index(normalized_modules)
    evidence = _scan_chunks(chunks, module_index)

    candidates: List[ExtractedFeature] = []
    seen_keys: Set[Tuple[str, frozenset]] = set()

    for idx, (feat_name, module_evidence) in enumerate(evidence.items(), start=1):
        # --- Block generic/subjective names ---
        if feat_name.lower() in _BLOCKED_NAMES:
            continue

        # --- Must have ≥ 1 source module ---
        source_modules = sorted(module_evidence.keys())
        if not source_modules:
            continue  # noise guard: no module support

        # --- Score ---
        confidence = _score_feature(feat_name, module_evidence, module_index)
        if confidence < 0.4:
            continue  # below noise floor

        # --- Deduplication key ---
        dedup_key = (feat_name, frozenset(source_modules))
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        # --- Count unique source files across all modules ---
        all_files = {
            fp
            for mod_files in module_evidence.values()
            for fp in mod_files.keys()
        }
        file_count = len(all_files)

        # --- Build description ---
        description = _make_description(
            FEATURE_REGISTRY[feat_name]["description"],
            source_modules,
            file_count,
        )

        candidates.append(
            ExtractedFeature(
                id=f"feat-{idx:03d}",
                name=feat_name,
                description=description,
                source_modules=source_modules,
                confidence=confidence,
            )
        )

    # --- Sort: confidence desc, then name asc ---
    candidates.sort(key=lambda f: (-f.confidence, f.name))

    # --- Re-index IDs after sort ---
    for i, feat in enumerate(candidates, start=1):
        feat.id = f"feat-{i:03d}"

    return FeatureExtractionResult(features=candidates)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "FeatureExtractionAgent: Extract real, module-backed features "
            "from normalized_modules + chunks. Returns JSON only."
        )
    )
    parser.add_argument(
        "--modules",
        default="runtime/outputs/normalized_context.json",
        help="Path to normalized_context.json (default: runtime/outputs/normalized_context.json)",
    )
    parser.add_argument(
        "--chunks",
        default="runtime/outputs/chunks_output.json",
        help="Path to chunks_output.json (default: runtime/outputs/chunks_output.json)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional path to write output JSON (prints to stdout if omitted)",
    )
    args = parser.parse_args()

    # --- Load inputs ---
    modules_path = Path(args.modules)
    chunks_path = Path(args.chunks)

    for p in (modules_path, chunks_path):
        if not p.exists():
            print(f"[ERROR] File not found: {p}", file=sys.stderr)
            raise SystemExit(1)

    with open(modules_path, encoding="utf-8") as fh:
        modules_raw = json.load(fh)

    with open(chunks_path, encoding="utf-8") as fh:
        chunks_raw = json.load(fh)

    # Support both { "normalized_modules": [...] } and bare list
    normalized_modules: List[Dict] = (
        modules_raw.get("normalized_modules", modules_raw)
        if isinstance(modules_raw, dict)
        else modules_raw
    )
    # Support both { "chunks": [...] } and bare list
    chunks: List[Dict] = (
        chunks_raw.get("chunks", chunks_raw)
        if isinstance(chunks_raw, dict)
        else chunks_raw
    )

    # --- Run ---
    result = extract_features(normalized_modules, chunks)
    output_json = result.model_dump_json(indent=2)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(output_json)
        print(f"[OK] Features written to {out_path}", file=sys.stderr)
    else:
        print(output_json)

    print(
        f"\n[SUMMARY] features_extracted={len(result.features)}",
        file=sys.stderr,
    )
