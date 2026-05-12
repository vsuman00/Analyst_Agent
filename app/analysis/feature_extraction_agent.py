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
  Uses an LLM to dynamically interpret the repository structure and content,
  identifying genuine functional and technical capabilities without relying
  on hardcoded generic keyword dictionaries.
"""

from __future__ import annotations

import json
import argparse
import sys
import os
from pathlib import Path
from typing import Dict, Any, List

from app.schemas.models import ExtractedFeature, FeatureExtractionResult

# Attempt to load environment variables and the LLM client
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(dotenv_path=_env_path, override=False)
except ImportError:
    pass

try:
    from app.utils.llm_client import llm_json_call
except ImportError:
    llm_json_call = None

DYNAMIC_EXTRACTION_PROMPT = """\
You are an expert software architect analyzing a codebase. I am providing you with the structural analysis of a software repository, including its core modules and summarized file contents.

Your task is to dynamically identify the core functional and technical features of this specific application. 
DO NOT hallucinate features. DO NOT use a generic list. Only extract features that have clear evidence in the provided files.

For example:
- If this is a Weather App, extract features like "Weather Data Fetching", "Location Persistence", or "UI Presentation Layer". 
- If it is a Web API, extract "REST API Routing", "Database Access", etc.
- If it is an AI tool, extract "LLM Prompting", "Context Processing", etc.

Return ONLY a valid JSON object matching this schema:
{
  "features": [
    {
      "name": "Feature Name (Title Case)",
      "description": "1-2 sentences explaining what it does and how it works based on the evidence.",
      "source_modules": ["Exact name of the module(s) from the input that prove this feature exists"],
      "confidence": 0.95
    }
  ]
}
"""

def extract_features(
    normalized_modules: List[Dict],
    chunks: List[Dict],
) -> FeatureExtractionResult:
    """
    Dynamically extract features using an LLM based on repository contents.
    """
    if llm_json_call is None or not os.environ.get("OPENAI_API_KEY"):
        print("[LLM] Feature extraction falling back to generic baseline (No API Key).", file=sys.stderr)
        return _fallback_extraction(normalized_modules)

    module_names = [m.get("name", "unknown") for m in normalized_modules]
    
    # Compress chunks to fit in context (take top N files, summarize contents)
    chunk_summaries = []
    for c in chunks[:50]: # limit to top 50 to avoid blowing up context window
        fp = c.get("file_path", "")
        content = c.get("content", "")[:300].replace("\n", " ") # snippet
        chunk_summaries.append(f"File: {fp} | Content snippet: {content}")
        
    context_str = (
        f"DETECTED MODULES: {', '.join(module_names)}\n\n"
        f"FILE SNIPPETS:\n" + "\n".join(chunk_summaries)
    )
    
    try:
        result = llm_json_call(DYNAMIC_EXTRACTION_PROMPT, context_str, max_tokens=1500)
        
        extracted = []
        raw_feats = result.get("features", [])
        for idx, rf in enumerate(raw_feats, start=1):
            extracted.append(ExtractedFeature(
                id=f"feat-{idx:03d}",
                name=rf.get("name", "Unknown Feature"),
                description=rf.get("description", "No description provided."),
                source_modules=rf.get("source_modules", []),
                confidence=float(rf.get("confidence", 0.8))
            ))
            
        if not extracted:
            print("[LLM] Dynamic feature extraction returned empty list. Using fallback.", file=sys.stderr)
            return _fallback_extraction(normalized_modules)
            
        return FeatureExtractionResult(features=extracted)
        
    except Exception as e:
        print(f"[LLM] Dynamic feature extraction failed: {e}. Using fallback.", file=sys.stderr)
        return _fallback_extraction(normalized_modules)

def _fallback_extraction(normalized_modules: List[Dict]) -> FeatureExtractionResult:
    """Deterministic fallback if LLM is unavailable or fails."""
    candidates = []
    for idx, mod in enumerate(normalized_modules, start=1):
        name = mod.get("name", "Unknown Module")
        candidates.append(
            ExtractedFeature(
                id=f"feat-{idx:03d}",
                name=name.replace("_", " ").title() + " Component",
                description=f"Core architectural component encompassing {name}.",
                source_modules=[name],
                confidence=0.7
            )
        )
    return FeatureExtractionResult(features=candidates)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "FeatureExtractionAgent: Extract dynamic features "
            "from normalized_modules + chunks using an LLM. Returns JSON only."
        )
    )
    parser.add_argument(
        "--modules",
        default="runtime/outputs/normalized_context.json",
        help="Path to normalized_context.json",
    )
    parser.add_argument(
        "--chunks",
        default="runtime/outputs/chunks_output.json",
        help="Path to chunks_output.json",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional path to write output JSON",
    )
    args = parser.parse_args()

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

    normalized_modules: List[Dict] = (
        modules_raw.get("normalized_modules", modules_raw)
        if isinstance(modules_raw, dict)
        else modules_raw
    )
    chunks: List[Dict] = (
        chunks_raw.get("chunks", chunks_raw)
        if isinstance(chunks_raw, dict)
        else chunks_raw
    )

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

    print(f"\n[SUMMARY] features_extracted={len(result.features)}", file=sys.stderr)