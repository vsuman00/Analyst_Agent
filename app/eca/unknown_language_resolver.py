"""
unknown_language_resolver.py — ECA Stage 1.2
---------------------------------------------
Hybrid Language Registry: LLM-backed resolver for unknown file extensions.

WHEN IT RUNS
  After FileClassifier (Stage 1.1) — which resolves extensions via the
  curated 'languages' block of language_registry.json — some file extensions
  may still be classified as "unknown". This module resolves those gaps using
  an LLM and permanently caches the results in the '_llm_inferred' block of
  language_registry.json so the LLM is never called again for the same extension.

LEARN & CACHE LIFECYCLE
  Run 1: .abcml unknown → LLM call → confidence 0.85
          → WRITE to '_llm_inferred' → reload_registry()
          → RepoContextBuilder sees .abcml as "backend"  ✅
  Run 2: .abcml → FOUND in '_llm_inferred' (static lookup)
          → ZERO LLM calls  ✅

ANTI-HALLUCINATION GUARDRAILS
  1. Bounded candidate list  — LLM is given all known language names to pick from
  2. Evidence citation       — LLM must quote the exact token that identifies the language
  3. Confidence threshold    — results below 0.7 are rejected (file stays "unknown")
  4. temperature=0           — enforced by llm_client.py
  5. Curated-wins rule       — '_llm_inferred' can never overwrite 'languages' entries

LARGE FILE HANDLING
  Only the first 800 characters of each file are sent to the LLM.
  Language identity is always visible in the first ~20 lines (imports,
  shebang, keywords) — the full file is never needed.

INVOCATION
  Called from runner.py between Stage 1.1 (FileClassifier) and Stage 3
  (ContentProcessor). Reads snippets directly from disk.

  overlay = resolve_unknown_languages(
      classified_data=classified_data,
      dest_repo_dir=dest_repo_dir,
      known_languages=list_all_languages(),
  )
"""

from __future__ import annotations

import json
import datetime
from pathlib import Path
from typing import Any, Dict, List

# llm_json_call is imported at module level so tests can patch it cleanly.
# If the LLM client is unavailable (no API key or import error), the
# resolve_unknown_languages() function silently returns {} before calling it.
try:
    from app.utils.llm_client import llm_json_call as llm_json_call
except ImportError:
    llm_json_call = None  # type: ignore[assignment]

# reload_registry is imported at module level so tests can patch it cleanly.
# The lazy local import inside _persist_inferences_to_registry would prevent patching.
from app.eca.language_loader import reload_registry

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SNIPPET_CHARS   = 800     # First N characters extracted per file
CONFIDENCE_MIN  = 0.7     # Minimum LLM confidence to accept an inference
REGISTRY_PATH   = Path(__file__).parent / "config" / "language_registry.json"

# ─────────────────────────────────────────────────────────────────────────────
# LLM Prompt
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a programming language classifier for a static code analysis pipeline.
You will be shown file content samples for file extensions that could not be
identified by a static language registry.

For each unknown extension:
  1. Try to identify the language from this bounded list if possible:
     {known_languages_csv}
     If the language is NOT in this list, name it as accurately as you can.
  2. Assign a role: "backend" | "frontend" | "config" | "docs"
  3. Quote the EXACT token from the provided content snippet that led to your
     conclusion (e.g. a keyword, import statement, shebang line, or comment syntax).
     This is REQUIRED. If you cannot find a concrete identifying token, set
     confidence to 0.0.
  4. Assign a confidence score 0.0–1.0 representing how certain you are.
     Use 0.0 if you genuinely cannot determine the language.
     NEVER fabricate a language name you are not confident about.

Return ONLY a single JSON object — no prose, no markdown:
{{
  "results": [
    {{
      "extension":  ".ext",
      "language":   "language_name_or_unknown",
      "role":       "backend|frontend|config|docs",
      "confidence": 0.0,
      "evidence":   "exact quoted token from snippet, or empty string if none found"
    }}
  ]
}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Public Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def resolve_unknown_languages(
    classified_data: Dict[str, Any],
    dest_repo_dir: Path,
    known_languages: List[str],
) -> Dict[str, Dict[str, Any]]:
    """
    Resolve file extensions that were classified as "unknown" by the static
    language registry.

    Algorithm:
      1. Collect all "unknown" file paths from classified_data.
      2. Deduplicate by extension — take one representative file per extension.
      3. Check _llm_inferred block — skip extensions already cached.
      4. Extract the first SNIPPET_CHARS characters from each representative file.
      5. Send one batched LLM call for ALL remaining unknown extensions.
      6. Accept results with confidence >= CONFIDENCE_MIN.
      7. Write accepted results to language_registry.json -> _llm_inferred.
      8. Call reload_registry() so the current run benefits immediately.

    Returns
    -------
    Dict mapping newly resolved extensions to their inferred definition dicts.
    Returns {} if nothing new was resolved (no unknowns, all already cached,
    or LLM unavailable).
    """
    # Step 1-2: collect unique unknown extensions from classified output
    ext_to_file = _collect_unknown_extensions(classified_data, dest_repo_dir)
    if not ext_to_file:
        return {}

    # Step 3: skip extensions already cached in _llm_inferred
    ext_to_file = _filter_already_inferred(ext_to_file)
    if not ext_to_file:
        print("[LANG RESOLVER] All unknown extensions already cached in _llm_inferred — no LLM call needed.")
        return {}

    print(f"[LANG RESOLVER] {len(ext_to_file)} unknown extension(s) need resolution: {list(ext_to_file.keys())}")

    # Step 4: extract content snippets from disk (first SNIPPET_CHARS chars only)
    snippets = _extract_snippets(ext_to_file, dest_repo_dir)
    if not snippets:
        print("[LANG RESOLVER] Could not read any file snippets — skipping.")
        return {}

    # Step 5-6: send batched LLM call and accept high-confidence results
    inferred = _call_llm_batch(snippets, known_languages)
    if not inferred:
        print("[LANG RESOLVER] LLM returned no high-confidence results.")
        return {}

    print(f"[LANG RESOLVER] Accepted {len(inferred)} inference(s): {list(inferred.keys())}")

    # Step 7-8: persist to _llm_inferred and invalidate LRU cache
    _persist_inferences_to_registry(inferred)

    return inferred


# ─────────────────────────────────────────────────────────────────────────────
# Internal Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _collect_unknown_extensions(
    classified_data: Dict[str, Any],
    dest_repo_dir: Path,
) -> Dict[str, Path]:
    """
    Walk classified_data and collect one representative absolute file path
    per unknown extension.

    Returns:  { ".abcml": Path("/path/to/some/file.abcml"), ... }
    """
    ext_to_file: Dict[str, Path] = {}

    classified_files = classified_data.get("classified_files", [])
    for entry in classified_files:
        # Only consider files the static registry couldn't identify
        if entry.get("category", "").lower() != "unknown":
            continue

        rel_path = entry.get("path", "")
        if not rel_path:
            continue

        ext = Path(rel_path).suffix.lower()
        if not ext or ext in ext_to_file:
            continue  # no extension or already have a representative

        abs_path = dest_repo_dir / rel_path
        if abs_path.is_file():
            ext_to_file[ext] = abs_path

    return ext_to_file


def _filter_already_inferred(ext_to_file: Dict[str, Path]) -> Dict[str, Path]:
    """
    Remove extensions that already have a cached entry in '_llm_inferred'.
    These are resolved statically — no LLM call needed.
    """
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            registry = json.load(f)
        inferred_block = registry.get("_llm_inferred", {})

        # Build a set of all extensions already cached
        cached_exts: set = set()
        for lang_def in inferred_block.values():
            if isinstance(lang_def, dict):
                for ext in lang_def.get("extensions", []):
                    cached_exts.add(ext.lower())

        return {
            ext: path
            for ext, path in ext_to_file.items()
            if ext not in cached_exts
        }
    except Exception as e:
        print(f"[LANG RESOLVER] Could not read _llm_inferred block (continuing): {e}")
        return ext_to_file  # proceed with all unknowns


def _extract_snippets(
    ext_to_file: Dict[str, Path],
    dest_repo_dir: Path,
) -> List[Dict[str, str]]:
    """
    For each extension, read the first SNIPPET_CHARS characters of the
    representative file from disk. Returns a list of snippet dicts.
    """
    snippets: List[Dict[str, str]] = []

    for ext, abs_path in ext_to_file.items():
        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
            snippet = content[:SNIPPET_CHARS].strip()
            if not snippet:
                continue  # empty file — skip

            # Make path relative for the prompt (easier for the LLM to use as context)
            try:
                rel_path = str(abs_path.relative_to(dest_repo_dir))
            except ValueError:
                rel_path = abs_path.name

            snippets.append({
                "extension": ext,
                "path":      rel_path,
                "content":   snippet,
            })
        except Exception as e:
            print(f"[LANG RESOLVER] Could not read {abs_path.name}: {e}")

    return snippets


def _call_llm_batch(
    snippets: List[Dict[str, str]],
    known_languages: List[str],
) -> Dict[str, Dict[str, Any]]:
    """
    Send a single batched LLM call for all unknown snippets.
    Returns a dict of accepted inferences (confidence >= CONFIDENCE_MIN):
    { ".abcml": {"language": "...", "role": "...", "confidence": 0.85, "evidence": "..."} }
    """
    if llm_json_call is None:
        print("[LANG RESOLVER] llm_client unavailable — skipping LLM batch call.")
        return {}

    # Build user prompt — one block per unknown extension
    blocks: List[str] = []
    for s in snippets:
        blocks.append(
            f"Extension: {s['extension']}\n"
            f"Path: {s['path']}\n"
            f"Content sample (first {SNIPPET_CHARS} chars):\n"
            f"```\n{s['content']}\n```"
        )

    user_prompt = (
        "Classify the following unknown file extensions based on the content samples below.\n\n"
        + "\n\n---\n\n".join(blocks)
    )

    system_prompt = _SYSTEM_PROMPT.format(
        known_languages_csv=", ".join(known_languages)
    )

    try:
        result = llm_json_call(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=800,
        )
    except Exception as e:
        print(f"[LANG RESOLVER] LLM call failed: {e}")
        return {}

    # Parse and filter by confidence threshold
    inferred: Dict[str, Dict[str, Any]] = {}
    today = datetime.date.today().isoformat()

    for item in result.get("results", []):
        ext        = item.get("extension", "").lower()
        language   = (item.get("language") or "").strip()
        role       = (item.get("role") or "backend").strip()
        confidence = float(item.get("confidence", 0.0))
        evidence   = (item.get("evidence") or "").strip()

        # Validation gates
        if not ext or not language or language.lower() in ("unknown", ""):
            continue
        if confidence < CONFIDENCE_MIN:
            print(f"[LANG RESOLVER] Rejected {ext!r} ({language}) — confidence {confidence:.2f} < {CONFIDENCE_MIN}")
            continue
        if role not in ("backend", "frontend", "config", "docs"):
            role = "backend"  # safe fallback

        inferred[ext] = {
            "language":    language,
            "role":        role,
            "confidence":  round(confidence, 4),
            "evidence":    evidence,
            "inferred_at": today,
        }

    return inferred


def _persist_inferences_to_registry(
    inferred: Dict[str, Dict[str, Any]],
) -> None:
    """
    Atomically appends accepted inferences to the '_llm_inferred' block in
    language_registry.json. Then calls reload_registry() so the current
    pipeline run benefits from the new entries immediately.

    SAFETY: Never touches the 'languages' (curated) block.
    ATOMICITY: Reads full JSON → merges → writes full JSON.
    """
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "_llm_inferred" not in data or not isinstance(data["_llm_inferred"], dict):
            data["_llm_inferred"] = {
                "_comment": (
                    "Auto-populated by UnknownLanguageResolver (Stage 1.2). "
                    "DO NOT edit manually — review and promote to 'languages' after verification."
                )
            }

        for ext, defn in inferred.items():
            # Convert extension to a safe JSON key (e.g. ".abcml" → "abcml")
            lang_key = defn["language"].lower().replace(" ", "_").replace("-", "_")

            # Avoid overwriting an existing _llm_inferred entry for this extension
            # (a later, possibly lower-confidence run should not clobber earlier results)
            existing_exts: set = set()
            for existing_def in data["_llm_inferred"].values():
                if isinstance(existing_def, dict):
                    for e in existing_def.get("extensions", []):
                        existing_exts.add(e.lower())
            if ext in existing_exts:
                continue  # already cached — do not overwrite

            data["_llm_inferred"][lang_key] = {
                "extensions":   [ext],
                "role":         defn["role"],
                "entry_points": [],
                "build_files":  [],
                "binary":       False,
                "confidence":   defn["confidence"],
                "evidence":     defn["evidence"],
                "inferred_at":  defn["inferred_at"],
                "promoted":     False,
                "notes": (
                    f"LLM-inferred at confidence={defn['confidence']}. "
                    "Evidence: " + defn["evidence"]
                ),
            }

        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"[LANG REGISTRY] Persisted {len(inferred)} inferred language(s) to registry → _llm_inferred.")

        # CRITICAL: invalidate LRU caches so current run sees the fresh entries
        reload_registry()

    except Exception as e:
        print(f"[LANG RESOLVER] Failed to persist inferences (non-blocking): {e}")
