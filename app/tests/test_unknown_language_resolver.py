"""
test_unknown_language_resolver.py
-----------------------------------
Unit tests for app.eca.unknown_language_resolver (Stage 1.2).

Covers:
  - Confidence threshold gate (< 0.7 rejected, >= 0.7 accepted)
  - Empty unknown list → zero LLM calls
  - Extension already cached in _llm_inferred → zero LLM calls
  - _persist_inferences_to_registry writes correctly to _llm_inferred block
  - reload_registry() is called after write
  - Two-tier lookup precedence: curated 'languages' wins over '_llm_inferred'
  - Malformed LLM JSON → graceful fallback, registry unchanged
  - Snippet extraction: only first SNIPPET_CHARS characters are used
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.eca.unknown_language_resolver import (
    CONFIDENCE_MIN,
    SNIPPET_CHARS,
    _call_llm_batch,
    _collect_unknown_extensions,
    _extract_snippets,
    _filter_already_inferred,
    _persist_inferences_to_registry,
    resolve_unknown_languages,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_registry(tmp_path):
    """Write a minimal language_registry.json to a temp file and patch the path."""
    reg = {
        "version": "1.1",
        "languages": {
            "python": {
                "extensions": [".py"],
                "role": "backend",
                "entry_points": ["main.py"],
                "build_files": ["requirements.txt"],
                "binary": False,
                "notes": "Python"
            }
        },
        "_llm_inferred": {
            "_comment": "Test registry"
        }
    }
    registry_file = tmp_path / "language_registry.json"
    registry_file.write_text(json.dumps(reg, indent=2))
    return registry_file


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a fake repo directory with a couple of unknown-extension files."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    # .abcml file — 1000 chars of fake content (only first 800 should be sent)
    fake_content = "PROGRAM DIVISION.\n DATA SECTION.\n " + "X" * 980
    (repo_dir / "grammar.abcml").write_text(fake_content, encoding="utf-8")

    # .xyz file
    (repo_dir / "config.xyz").write_text("config: true\nversion: 2\n", encoding="utf-8")

    return repo_dir


@pytest.fixture
def classified_unknown(tmp_repo):
    """classified_data with two unknown-category entries."""
    return {
        "classified_files": [
            {"path": "grammar.abcml", "category": "unknown", "confidence": 0.0},
            {"path": "config.xyz",    "category": "unknown", "confidence": 0.0},
            {"path": "main.py",       "category": "backend", "confidence": 0.95},
        ]
    }


# ─────────────────────────────────────────────────────────────────────────────
# _collect_unknown_extensions
# ─────────────────────────────────────────────────────────────────────────────

class TestCollectUnknownExtensions:
    def test_picks_one_repr_per_extension(self, classified_unknown, tmp_repo):
        result = _collect_unknown_extensions(classified_unknown, tmp_repo)
        assert set(result.keys()) == {".abcml", ".xyz"}

    def test_skips_non_unknown_categories(self, tmp_repo):
        classified = {
            "classified_files": [
                {"path": "main.py", "category": "backend", "confidence": 0.95},
            ]
        }
        result = _collect_unknown_extensions(classified, tmp_repo)
        assert result == {}

    def test_skips_missing_files(self, tmp_repo):
        classified = {
            "classified_files": [
                {"path": "ghost.abcml", "category": "unknown", "confidence": 0.0},
            ]
        }
        result = _collect_unknown_extensions(classified, tmp_repo)
        assert result == {}


# ─────────────────────────────────────────────────────────────────────────────
# _filter_already_inferred
# ─────────────────────────────────────────────────────────────────────────────

class TestFilterAlreadyInferred:
    def test_removes_cached_extension(self, tmp_registry, tmp_repo):
        # Seed the registry with .abcml already cached
        reg = json.loads(tmp_registry.read_text())
        reg["_llm_inferred"]["custdsl"] = {
            "extensions": [".abcml"],
            "role": "backend",
            "promoted": False
        }
        tmp_registry.write_text(json.dumps(reg))

        ext_to_file = {".abcml": tmp_repo / "grammar.abcml", ".xyz": tmp_repo / "config.xyz"}

        with patch("app.eca.unknown_language_resolver.REGISTRY_PATH", tmp_registry):
            result = _filter_already_inferred(ext_to_file)

        assert ".abcml" not in result
        assert ".xyz" in result

    def test_keeps_all_when_none_cached(self, tmp_registry, tmp_repo):
        ext_to_file = {".abcml": tmp_repo / "grammar.abcml"}
        with patch("app.eca.unknown_language_resolver.REGISTRY_PATH", tmp_registry):
            result = _filter_already_inferred(ext_to_file)
        assert ".abcml" in result


# ─────────────────────────────────────────────────────────────────────────────
# _extract_snippets
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractSnippets:
    def test_truncates_to_snippet_chars(self, tmp_repo):
        ext_to_file = {".abcml": tmp_repo / "grammar.abcml"}
        snippets = _extract_snippets(ext_to_file, tmp_repo)
        assert len(snippets) == 1
        assert len(snippets[0]["content"]) <= SNIPPET_CHARS

    def test_skips_unreadable_file(self, tmp_repo):
        ext_to_file = {".ghost": tmp_repo / "nonexistent.ghost"}
        snippets = _extract_snippets(ext_to_file, tmp_repo)
        assert snippets == []


# ─────────────────────────────────────────────────────────────────────────────
# _call_llm_batch — confidence threshold gate
# ─────────────────────────────────────────────────────────────────────────────

class TestCallLlmBatch:
    def _make_snippets(self):
        return [
            {"extension": ".abcml", "path": "grammar.abcml", "content": "PROGRAM DIVISION."},
            {"extension": ".xyz",   "path": "config.xyz",    "content": "config: true"},
        ]

    def test_accepts_high_confidence(self):
        llm_response = {
            "results": [{
                "extension":  ".abcml",
                "language":   "CustomDSL",
                "role":       "backend",
                "confidence": 0.85,
                "evidence":   "PROGRAM DIVISION keyword"
            }]
        }
        with patch("app.eca.unknown_language_resolver.llm_json_call", return_value=llm_response):
            result = _call_llm_batch(self._make_snippets(), ["python", "cobol"])
        assert ".abcml" in result
        assert result[".abcml"]["language"] == "CustomDSL"
        assert result[".abcml"]["role"] == "backend"

    def test_rejects_low_confidence(self):
        llm_response = {
            "results": [{
                "extension":  ".abcml",
                "language":   "MaybeLang",
                "role":       "backend",
                "confidence": 0.5,         # below 0.7 threshold
                "evidence":   "not sure"
            }]
        }
        with patch("app.eca.unknown_language_resolver.llm_json_call", return_value=llm_response):
            result = _call_llm_batch(self._make_snippets(), ["python"])
        assert result == {}

    def test_rejects_unknown_language_name(self):
        llm_response = {
            "results": [{
                "extension":  ".xyz",
                "language":   "unknown",
                "role":       "backend",
                "confidence": 0.9,
                "evidence":   ""
            }]
        }
        with patch("app.eca.unknown_language_resolver.llm_json_call", return_value=llm_response):
            result = _call_llm_batch(self._make_snippets(), ["python"])
        assert result == {}

    def test_handles_malformed_llm_response(self):
        """LLM raises exception — graceful fallback, no crash."""
        with patch("app.eca.unknown_language_resolver.llm_json_call", side_effect=Exception("LLM error")):
            result = _call_llm_batch(self._make_snippets(), ["python"])
        assert result == {}

    def test_normalises_invalid_role(self):
        llm_response = {
            "results": [{
                "extension":  ".abcml",
                "language":   "CustomDSL",
                "role":       "gibberish",  # invalid role → normalised to "backend"
                "confidence": 0.88,
                "evidence":   "PROGRAM DIVISION"
            }]
        }
        with patch("app.eca.unknown_language_resolver.llm_json_call", return_value=llm_response):
            result = _call_llm_batch(self._make_snippets(), ["python"])
        assert result[".abcml"]["role"] == "backend"


# ─────────────────────────────────────────────────────────────────────────────
# _persist_inferences_to_registry
# ─────────────────────────────────────────────────────────────────────────────

class TestPersistInferencesToRegistry:
    def test_writes_to_llm_inferred_block(self, tmp_registry):
        inferred = {
            ".abcml": {
                "language":    "CustomDSL",
                "role":        "backend",
                "confidence":  0.85,
                "evidence":    "PROGRAM DIVISION keyword",
                "inferred_at": "2026-05-29",
            }
        }
        with patch("app.eca.unknown_language_resolver.REGISTRY_PATH", tmp_registry), \
             patch("app.eca.unknown_language_resolver.reload_registry"):
            _persist_inferences_to_registry(inferred)

        saved = json.loads(tmp_registry.read_text())
        # "CustomDSL" → lowercased → "customdsl"
        assert "customdsl" in saved["_llm_inferred"]
        entry = saved["_llm_inferred"]["customdsl"]
        assert entry["extensions"] == [".abcml"]
        assert entry["role"] == "backend"
        assert entry["promoted"] is False

    def test_never_touches_languages_block(self, tmp_registry):
        inferred = {
            ".abcml": {
                "language": "CustomDSL", "role": "backend",
                "confidence": 0.9, "evidence": "X", "inferred_at": "2026-05-29"
            }
        }
        with patch("app.eca.unknown_language_resolver.REGISTRY_PATH", tmp_registry), \
             patch("app.eca.unknown_language_resolver.reload_registry"):
            _persist_inferences_to_registry(inferred)

        saved = json.loads(tmp_registry.read_text())
        # 'languages' block must still only have 'python'
        assert list(saved["languages"].keys()) == ["python"]

    def test_does_not_overwrite_existing_inference(self, tmp_registry):
        """A second run with the same extension should not overwrite the first result."""
        # Seed existing entry
        reg = json.loads(tmp_registry.read_text())
        reg["_llm_inferred"]["custdsl"] = {
            "extensions": [".abcml"], "role": "backend",
            "confidence": 0.91, "promoted": False
        }
        tmp_registry.write_text(json.dumps(reg))

        inferred = {
            ".abcml": {
                "language": "CustomDSL", "role": "frontend",  # different role
                "confidence": 0.75, "evidence": "X", "inferred_at": "2026-05-30"
            }
        }
        with patch("app.eca.unknown_language_resolver.REGISTRY_PATH", tmp_registry), \
             patch("app.eca.unknown_language_resolver.reload_registry"):
            _persist_inferences_to_registry(inferred)

        saved = json.loads(tmp_registry.read_text())
        # First result preserved — role still "backend", confidence still 0.91
        assert saved["_llm_inferred"]["custdsl"]["role"] == "backend"
        assert saved["_llm_inferred"]["custdsl"]["confidence"] == 0.91

    def test_calls_reload_registry_after_write(self, tmp_registry):
        inferred = {
            ".abcml": {
                "language": "CustomDSL", "role": "backend",
                "confidence": 0.85, "evidence": "X", "inferred_at": "2026-05-29"
            }
        }
        with patch("app.eca.unknown_language_resolver.REGISTRY_PATH", tmp_registry), \
             patch("app.eca.unknown_language_resolver.reload_registry") as mock_reload:
            _persist_inferences_to_registry(inferred)
        mock_reload.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Two-Tier Lookup Precedence (language_loader)
# ─────────────────────────────────────────────────────────────────────────────

class TestTwoTierLookupPrecedence:
    def test_curated_wins_over_inferred_on_collision(self, tmp_registry, tmp_repo):
        """If .py is in both 'languages' and '_llm_inferred', curated must win."""
        from app.eca.language_loader import get_role, reload_registry

        # Build a controlled registry where _llm_inferred claims .py with frontend role
        controlled_registry = {
            "version": "1.1",
            "languages": {
                "python": {
                    "extensions": [".py"],
                    "role":       "backend",     # curated role
                    "entry_points": ["main.py"],
                    "build_files": ["requirements.txt"],
                    "binary": False,
                    "notes": "Python"
                }
            },
            "_llm_inferred": {
                "fake_python": {
                    "extensions": [".py"],
                    "role":       "frontend",    # wrong role — must NOT win
                    "promoted":   False
                }
            }
        }

        # Patch _load_registry so all cache functions see our controlled dict
        with patch("app.eca.language_loader._load_registry", return_value=controlled_registry):
            reload_registry()  # clear LRU so patched _load_registry is called
            role = get_role(".py")

        # Curated python role "backend" must NOT be overridden by _llm_inferred entry
        assert role == "backend"


# ─────────────────────────────────────────────────────────────────────────────
# resolve_unknown_languages — zero LLM calls when nothing is unknown
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveUnknownLanguages:
    def test_no_llm_call_when_no_unknowns(self, tmp_repo, tmp_registry):
        classified = {
            "classified_files": [
                {"path": "main.py", "category": "backend", "confidence": 0.95},
            ]
        }
        with patch("app.eca.unknown_language_resolver.REGISTRY_PATH", tmp_registry):
            with patch("app.eca.unknown_language_resolver.llm_json_call") as mock_llm:
                result = resolve_unknown_languages(classified, tmp_repo, ["python"])
        assert result == {}
        mock_llm.assert_not_called()

    def test_no_llm_call_when_all_already_cached(self, tmp_repo, tmp_registry):
        reg = json.loads(tmp_registry.read_text())
        reg["_llm_inferred"]["abcml_lang"] = {
            "extensions": [".abcml"], "role": "backend", "promoted": False
        }
        reg["_llm_inferred"]["xyz_lang"] = {
            "extensions": [".xyz"], "role": "config", "promoted": False
        }
        tmp_registry.write_text(json.dumps(reg))

        classified = {
            "classified_files": [
                {"path": "grammar.abcml", "category": "unknown", "confidence": 0.0},
                {"path": "config.xyz",    "category": "unknown", "confidence": 0.0},
            ]
        }
        with patch("app.eca.unknown_language_resolver.REGISTRY_PATH", tmp_registry):
            with patch("app.eca.unknown_language_resolver.llm_json_call") as mock_llm:
                result = resolve_unknown_languages(classified, tmp_repo, ["python"])

        assert result == {}
        mock_llm.assert_not_called()
