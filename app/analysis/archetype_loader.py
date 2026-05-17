"""
archetype_loader.py — Analysis Config Registry Engine
-------------------------------------------------------
Loads and caches the archetype_registry.json config and exposes a single
lookup function consumed by ProductUnderstandingAgent.

DESIGN RULE: All archetype/domain-signal knowledge lives in archetype_registry.json.
This module is a pure data reader — it contains NO hardcoded archetype facts.

Adding a new archetype (e.g., "healthcare_platform"):
    1. Open app/analysis/config/archetype_registry.json
    2. Add a new entry under "archetypes" with keywords, display, and fragment.
    3. Zero Python changes required.

Public API:
    get_domain_signals()  → Dict[str, Dict]
        Returns a dict matching the original DOMAIN_SIGNALS shape:
        {
          "archetype_key": {
            "keywords": set[str],   ← JSON array converted to set for O(1) lookup
            "display":  str,
            "fragment": str,
          },
          ...
        }

    reload_registry()     → None
        Force-clears the cache (useful for hot-reload in long-running servers).
"""

from __future__ import annotations

import json
import functools
from pathlib import Path
from typing import Dict, Any, Set

# ─── Registry Path ─────────────────────────────────────────────────────────────
_REGISTRY_PATH = Path(__file__).parent / "config" / "archetype_registry.json"


# ─── Internal Cache ────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def _load_registry() -> Dict[str, Any]:
    """Load the archetype registry JSON once and cache it for the process lifetime."""
    if not _REGISTRY_PATH.exists():
        raise FileNotFoundError(
            f"Archetype registry not found at: {_REGISTRY_PATH}\n"
            "Please ensure app/analysis/config/archetype_registry.json exists."
        )
    with open(_REGISTRY_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


@functools.lru_cache(maxsize=1)
def _build_domain_signals() -> Dict[str, Dict]:
    """
    Convert the JSON registry into the DOMAIN_SIGNALS shape expected by
    ProductUnderstandingAgent:

    {
      "archetype_key": {
        "keywords": set[str],   ← converted from JSON array for O(1) lookup
        "display":  str,
        "fragment": str,
      }
    }
    """
    reg = _load_registry()
    signals: Dict[str, Dict] = {}
    for key, spec in reg.get("archetypes", {}).items():
        signals[key] = {
            "keywords": set(spec.get("keywords", [])),  # list → set
            "display":  spec.get("display", key.replace("_", " ").title()),
            "fragment": spec.get("fragment", ""),
        }
    return signals


# ─── Public API ────────────────────────────────────────────────────────────────

def get_domain_signals() -> Dict[str, Dict]:
    """
    Return the full domain signal map loaded from archetype_registry.json.

    Each entry has the shape:
      { "keywords": set[str], "display": str, "fragment": str }

    The result is cached after the first call for the process lifetime.
    Call reload_registry() to force a fresh read.
    """
    return _build_domain_signals()


def list_archetypes() -> list[str]:
    """Return a sorted list of all registered archetype keys."""
    return sorted(_load_registry().get("archetypes", {}).keys())


def reload_registry() -> None:
    """
    Force-clear all caches so that a modified archetype_registry.json
    is re-read on the next call. Useful for hot-reload in long-running servers.
    """
    _load_registry.cache_clear()
    _build_domain_signals.cache_clear()


# ─── CLI self-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Archetype Registry Self-Test ===\n")
    signals = get_domain_signals()
    for key, spec in signals.items():
        kw_preview = ", ".join(sorted(spec["keywords"])[:4])
        print(f"  {key:<25} → display='{spec['display']}'  keywords=[{kw_preview}, ...]")
    print(f"\nTotal registered archetypes: {len(signals)}")
    print(f"Registered archetypes: {list_archetypes()}")
