"""
evidence_bundle.py — Evidence Bundle Builder
----------------------------------------------
Aggregates ALL deterministically extracted facts into one structured JSON object
before the LLM sees anything. This is the anti-hallucination foundation.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.utils.logger import get_logger, log

logger = get_logger(__name__)

_MAX_CHUNKS      = 15
_MAX_CHUNK_CHARS = 400


def build_evidence_bundle(
    *,
    scan_data:       Dict[str, Any],
    validated_feats: List[Dict],
    frs:             List[Dict],
    nfrs:            List[Dict],
    biz_ctx:         Dict[str, Any],
    chunks:          List[Dict],
    dependencies:    Dict[str, Any],
    entities:        Dict[str, Any],
    api_endpoints:   Dict[str, Any],
    defects:         Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the Evidence Bundle from all pipeline stage outputs.
    All parameters are keyword-only to prevent positional mismatches.
    """
    repo_name  = scan_data.get("repo_name", "Unknown Repository")
    lang       = dependencies.get("language", "unknown")
    build_tool = dependencies.get("build_tool", "unknown")
    jcenter    = dependencies.get("uses_jcenter", False)
    deps       = dependencies.get("dependencies", [])
    ent_list   = entities.get("entities", [])
    ep_list    = api_endpoints.get("endpoints", [])
    grpc_list  = api_endpoints.get("grpc_rpcs", [])
    defect_list= defects.get("defects", [])
    ptype      = biz_ctx.get("product_type", "Software System")
    users      = biz_ctx.get("primary_users", [])
    cvalue     = biz_ctx.get("core_value", "")
    caps       = biz_ctx.get("core_capabilities", [])
    psummary   = biz_ctx.get("product_summary", "")

    high_conf       = [f for f in validated_feats if float(f.get("confidence", 0)) >= 0.8]
    low_conf        = [f for f in validated_feats if float(f.get("confidence", 0)) < 0.6]
    critical_defects= [d for d in defect_list if d.get("severity") == "critical"]

    stats = {
        "total_features":     len(validated_feats),
        "high_conf_features": len(high_conf),
        "low_conf_features":  len(low_conf),
        "critical_defects":   len(critical_defects),
        "total_endpoints":    len(ep_list),
        "total_entities":     len(ent_list),
        "total_defects":      len(defect_list),
    }

    top_chunks = [
        {
            "file_path": c.get("file_path", c.get("file", "")),
            "content":   c.get("content", "")[:_MAX_CHUNK_CHARS],
        }
        for c in chunks[:_MAX_CHUNKS]
    ]

    bundle: Dict[str, Any] = {
        "repo_name":       repo_name,
        "language":        lang,
        "build_tool":      build_tool,
        "uses_jcenter":    jcenter,
        "product_type":    ptype,
        "primary_users":   users,
        "core_value":      cvalue,
        "core_capabilities": caps,
        "product_summary": psummary,
        "features":                    validated_feats,
        "functional_requirements":     frs,
        "non_functional_requirements": nfrs,
        "dependencies":    deps,
        "entities":        ent_list,
        "endpoints":       ep_list,
        "grpc_rpcs":       grpc_list,
        "defects":         defect_list,
        "stats":           stats,
        "top_chunks":      top_chunks,
    }

    log(logger.info, "evidence_bundle.built",
        repo=repo_name, features=len(validated_feats),
        deps=len(deps), entities=len(ent_list),
        endpoints=len(ep_list), defects=len(defect_list))

    return bundle
