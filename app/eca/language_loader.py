"""
language_loader.py — ECA Language Registry Engine
---------------------------------------------------
Loads and caches the language_registry.json config and exposes simple
lookup functions consumed by all other ECA tools.

DESIGN RULE: All language knowledge lives in language_registry.json.
This module is a pure data reader — it contains NO hardcoded language facts.

Two-Tier Lookup Order (highest → lowest priority):
  1. "languages"     block — human-curated, committed to source control
  2. "_llm_inferred" block — auto-written by UnknownLanguageResolver (Stage 1.2)

Curated entries ALWAYS win on extension collision.
Both tiers are LRU-cached; reload_registry() clears both.

Public API:
    get_role(extension)        → "backend" | "frontend" | "config" | "docs" | "unknown"
    get_language(extension)    → "python" | "cobol" | "powerbuilder" | ... | "unknown"
    is_binary(extension)       → True if the file should be skipped by scanners
    is_entry_point(filename)   → True if the filename is a known app entry-point
    get_ignore_dirs()          → set of directory names to skip during os.walk
    get_build_file_names()     → set of known build file names (package.json, pom.xml …)
    describe(extension)        → full dict for the language owning this extension, or {}
    list_all_languages()       → sorted list of all registered language names (both tiers)
    reload_registry()          → force-clear all LRU caches (call after writing _llm_inferred)
"""

from __future__ import annotations

import json
import functools
from pathlib import Path
from typing import Dict, Set, List, Any

# ─── Registry Path ────────────────────────────────────────────────────────────
_REGISTRY_PATH = Path(__file__).parent / "config" / "language_registry.json"


# ─── Internal Cache ───────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def _load_registry() -> Dict[str, Any]:
    """Load the registry JSON once and cache it for the process lifetime."""
    if not _REGISTRY_PATH.exists():
        raise FileNotFoundError(
            f"Language registry not found at: {_REGISTRY_PATH}\n"
            "Please ensure app/eca/config/language_registry.json exists."
        )
    with open(_REGISTRY_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


@functools.lru_cache(maxsize=1)
def _build_ext_to_language() -> Dict[str, str]:
    """
    Build a flat map:  extension → language_name
    e.g. ".py" → "python", ".cbl" → "cobol", ".pbl" → "powerbuilder"

    Reads both 'languages' (curated) and '_llm_inferred' (LLM-learned).
    Curated entries take precedence on any extension collision — LLM
    can never overwrite a human-authored registry entry.
    """
    reg = _load_registry()
    mapping: Dict[str, str] = {}

    # 1. Curated languages — highest priority, committed to source control
    for lang_name, lang_def in reg.get("languages", {}).items():
        for ext in lang_def.get("extensions", []):
            ext_lower = ext.lower()
            if ext_lower not in mapping:
                mapping[ext_lower] = lang_name

    # 2. LLM-inferred languages — lower priority, auto-written by Stage 1.2
    #    Only fills gaps not covered by curated block.
    for lang_name, lang_def in reg.get("_llm_inferred", {}).items():
        if lang_name.startswith("_"):          # skip _comment and meta keys
            continue
        for ext in lang_def.get("extensions", []):
            ext_lower = ext.lower()
            if ext_lower not in mapping:       # never overwrite a curated entry
                mapping[ext_lower] = lang_name

    return mapping


@functools.lru_cache(maxsize=1)
def _build_binary_set() -> Set[str]:
    reg = _load_registry()
    return {e.lower() for e in reg.get("universal_binary_extensions", [])}


@functools.lru_cache(maxsize=1)
def _build_config_ext_set() -> Set[str]:
    reg = _load_registry()
    return {e.lower() for e in reg.get("universal_config_extensions", [])}


@functools.lru_cache(maxsize=1)
def _build_doc_ext_set() -> Set[str]:
    reg = _load_registry()
    return {e.lower() for e in reg.get("universal_doc_extensions", [])}


@functools.lru_cache(maxsize=1)
def _build_ignore_dirs() -> Set[str]:
    reg = _load_registry()
    return set(reg.get("ignore_dirs", []))


@functools.lru_cache(maxsize=1)
def _build_entry_points() -> Set[str]:
    """Collect every known entry-point filename across all languages."""
    reg = _load_registry()
    eps: Set[str] = set()
    for lang_def in reg.get("languages", {}).values():
        for ep in lang_def.get("entry_points", []):
            eps.add(ep.lower())
    return eps


@functools.lru_cache(maxsize=1)
def _build_build_file_names() -> Set[str]:
    """Collect every known build-file name across all languages (basename only)."""
    reg = _load_registry()
    bfiles: Set[str] = set()
    for lang_def in reg.get("languages", {}).values():
        for bf in lang_def.get("build_files", []):
            bfiles.add(Path(bf).name.lower())
    return bfiles


# ─── Public API ───────────────────────────────────────────────────────────────

def get_language(extension: str) -> str:
    """
    Return the canonical language name for a given file extension.

    Examples:
        get_language(".py")   → "python"
        get_language(".cbl")  → "cobol"
        get_language(".pbl")  → "powerbuilder"
        get_language(".xyz")  → "unknown"
    """
    ext = extension.lower()
    return _build_ext_to_language().get(ext, "unknown")


def get_role(extension: str) -> str:
    """
    Return the high-level role for a file extension.

    Returns one of: "frontend" | "backend" | "config" | "docs" | "unknown"

    Resolution order:
      1. Universal config extensions  (yaml, toml, ini …)
      2. Universal doc extensions     (md, rst, txt …)
      3. Universal binary extensions  → "binary" (internal, callers should use is_binary())
      4. Language-specific role — checked in 'languages' first, then '_llm_inferred'
      5. "unknown" fallback
    """
    ext = extension.lower()

    if ext in _build_config_ext_set():
        return "config"
    if ext in _build_doc_ext_set():
        return "docs"
    if ext in _build_binary_set():
        return "binary"

    lang_name = _build_ext_to_language().get(ext)
    if lang_name:
        reg = _load_registry()
        # Check curated block first, then _llm_inferred (curated always wins)
        lang_def = (
            reg["languages"].get(lang_name)
            or reg.get("_llm_inferred", {}).get(lang_name)
            or {}
        )
        return lang_def.get("role", "unknown")

    return "unknown"


def is_binary(extension: str) -> bool:
    """Return True if the extension is in the universal binary list."""
    return extension.lower() in _build_binary_set()


def is_entry_point(filename: str) -> bool:
    """
    Return True if the filename (basename only) is a known application entry-point.

    Example: is_entry_point("main.py") → True
             is_entry_point("utils.py") → False
    """
    return Path(filename).name.lower() in _build_entry_points()


def get_ignore_dirs() -> Set[str]:
    """Return the set of directory names that scanners should skip."""
    return _build_ignore_dirs()


def get_build_file_names() -> Set[str]:
    """Return basenames of all known build/manifest files (package.json, pom.xml …)."""
    return _build_build_file_names()


def describe(extension: str) -> Dict[str, Any]:
    """
    Return the full language definition dict for the language that owns this extension.
    Returns {} if the extension is not registered in either tier.

    Example:
        describe(".swift") →
        {
          "extensions": [".swift"],
          "role": "frontend",
          "entry_points": ["main.swift", "AppDelegate.swift", ...],
          "build_files": ["Package.swift", "Podfile", "Cartfile"],
          "binary": false,
          "notes": "Apple ecosystem: iOS, macOS, watchOS, tvOS"
        }
    """
    lang_name = get_language(extension)
    if lang_name == "unknown":
        return {}
    reg = _load_registry()
    # Check curated block first, then _llm_inferred
    return (
        reg["languages"].get(lang_name)
        or reg.get("_llm_inferred", {}).get(lang_name)
        or {}
    )


def list_all_languages() -> List[str]:
    """
    Return a sorted list of all registered language names from both tiers.
    Includes curated 'languages' and LLM-inferred '_llm_inferred' entries.
    Meta-keys (starting with '_') are excluded.
    """
    reg = _load_registry()
    curated  = set(reg.get("languages", {}).keys())
    inferred = {k for k in reg.get("_llm_inferred", {}).keys() if not k.startswith("_")}
    return sorted(curated | inferred)


def reload_registry() -> None:
    """
    Force-clear all caches so that a modified language_registry.json
    is re-read on the next call. Useful for hot-reload in long-running servers.
    """
    _load_registry.cache_clear()
    _build_ext_to_language.cache_clear()
    _build_binary_set.cache_clear()
    _build_config_ext_set.cache_clear()
    _build_doc_ext_set.cache_clear()
    _build_ignore_dirs.cache_clear()
    _build_entry_points.cache_clear()
    _build_build_file_names.cache_clear()


# ─── CLI self-test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Language Registry Self-Test ===\n")
    test_cases = [
        (".py", "python"),
        (".cbl", "cobol"),
        (".pbl", "powerbuilder"),
        (".frm", "vb6"),
        (".swift", "swift"),
        (".ts", "typescript"),
        (".rs", "rust"),
        (".abap", "abap"),
        (".png", "unknown"),   # binary
        (".xyz", "unknown"),   # truly unknown
    ]
    all_passed = True
    for ext, expected_lang in test_cases:
        actual_lang = get_language(ext)
        actual_role = get_role(ext)
        status = "✓" if actual_lang == expected_lang else "✗"
        if actual_lang != expected_lang:
            all_passed = False
        print(f"  {status}  {ext:<10} → lang={actual_lang:<15} role={actual_role}")

    print(f"\nEntry-point checks:")
    for name in ["main.py", "AppDelegate.swift", "utils.py", "main.cob"]:
        print(f"  is_entry_point({name!r}) = {is_entry_point(name)}")

    print(f"\nTotal registered languages: {len(list_all_languages())}")
    print(f"{'ALL PASSED' if all_passed else 'SOME TESTS FAILED'}")
