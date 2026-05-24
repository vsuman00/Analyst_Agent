"""
skill_matcher.py — Layer 3 Tool
---------------------------------
Scores all loaded skill packs against repository evidence signals.

The scoring algorithm is entirely data-driven:
  - Detection rules live in each SKILL.md's YAML frontmatter (detection_signals)
  - No skill pack names, IDs, or domain knowledge is hardcoded here
  - When no pack scores above threshold → triggers skill_composer.py

Scoring dimensions:
  1. evidence_flags      : boolean flags from RepoEvidenceManifest (+1.0 each)
  2. dependency_keywords : package names matched against detected deps (+0.8 each)
  3. file_patterns       : glob-style patterns matched against file tree (+0.6 each)

Each dimension's scores are summed and normalized to 0.0–1.0.
A skill activates when its score >= its own confidence_threshold (default 0.6).
"""

from __future__ import annotations

import fnmatch
import sys
from typing import Dict, List, Any, Tuple

from app.skills.skill_loader import LoadedSkill, load_all_skills


# ---------------------------------------------------------------------------
# Pattern Matching Helper
# ---------------------------------------------------------------------------

def _matches_pattern(pattern: str, file_paths: List[str]) -> bool:
    """
    Check if any file path matches a glob-style pattern.
    Supports ** for directory wildcards (e.g. "**/routes/**").
    """
    # Normalise pattern — fnmatch doesn't natively handle **
    # so we check each file individually.
    for fp in file_paths:
        fp_lower = fp.lower().replace("\\", "/")
        pattern_lower = pattern.lower().replace("\\", "/")

        # Direct fnmatch (handles *.proto, **/routes/*, etc.)
        if fnmatch.fnmatch(fp_lower, pattern_lower):
            return True

        # Handle **/segment patterns by checking suffix
        if pattern_lower.startswith("**/"):
            suffix = pattern_lower[3:]
            if fnmatch.fnmatch(fp_lower, suffix) or \
               fnmatch.fnmatch(fp_lower, "*/" + suffix):
                return True

            # Also check if any segment matches
            parts = fp_lower.split("/")
            for i in range(len(parts)):
                remainder = "/".join(parts[i:])
                if fnmatch.fnmatch(remainder, suffix):
                    return True

    return False


# ---------------------------------------------------------------------------
# Scoring Engine
# ---------------------------------------------------------------------------

def score_skill(
    skill: LoadedSkill,
    evidence: Dict[str, Any],
    repo_context: Dict[str, Any],
    detected_deps: List[Dict[str, Any]],
) -> float:
    """
    Score a single skill pack against repo evidence.

    Scoring uses a MAX-OF-DIMENSIONS approach:
    - Each dimension (evidence, deps, patterns) produces its own 0.0–1.0 score
    - Final score = max across all dimensions
    - Bonus +0.15 when multiple dimensions fire simultaneously

    This prevents large keyword lists from diluting strong single-dimension matches.
    """
    signals = skill.detection_signals
    if not signals or not isinstance(signals, dict):
        return 0.0

    dim_scores = []

    # ── Dimension 1: evidence_flags (binary match: any flag true = 1.0) ──
    ev_flags = signals.get("evidence_flags", [])
    if ev_flags:
        matched = sum(1 for f in ev_flags if evidence.get(f, False))
        # Score = fraction of flags matched (at least one → strong signal)
        ev_score = matched / len(ev_flags) if ev_flags else 0.0
        dim_scores.append(ev_score)

    # ── Dimension 2: dependency_keywords (any match = strong signal) ──────
    dep_kws = signals.get("dependency_keywords", [])
    if dep_kws:
        dep_names_lower = set()
        for d in detected_deps:
            name = ""
            if isinstance(d, dict):
                name = d.get("name", "")
            elif isinstance(d, str):
                name = d
            if name:
                dep_names_lower.add(name.lower())

        matched_deps = 0
        for kw in dep_kws:
            kw_lower = kw.lower()
            if kw_lower in dep_names_lower or any(kw_lower in d for d in dep_names_lower):
                matched_deps += 1

        # Score: saturates quickly — 1 match = 0.6, 2 = 0.8, 3+ = 1.0
        if matched_deps >= 3:
            dep_score = 1.0
        elif matched_deps == 2:
            dep_score = 0.8
        elif matched_deps == 1:
            dep_score = 0.6
        else:
            dep_score = 0.0
        dim_scores.append(dep_score)

    # ── Dimension 3: file_patterns (any match = moderate signal) ──────────
    fp_patterns = signals.get("file_patterns", [])
    if fp_patterns:
        structure = repo_context.get("structure", {})
        flat_files: List[str] = []
        for group_files in structure.values():
            if isinstance(group_files, list):
                flat_files.extend(group_files)

        file_tree = repo_context.get("file_tree", {})
        if isinstance(file_tree, dict):
            flat_files.extend(file_tree.keys())

        matched_patterns = sum(1 for p in fp_patterns if _matches_pattern(p, flat_files))

        if matched_patterns >= 3:
            fp_score = 1.0
        elif matched_patterns == 2:
            fp_score = 0.7
        elif matched_patterns == 1:
            fp_score = 0.5
        else:
            fp_score = 0.0
        dim_scores.append(fp_score)

    if not dim_scores:
        return 0.0

    # Final score = max of all dimensions
    base_score = max(dim_scores)

    # Bonus: if multiple dimensions fire, boost the score
    firing_dims = sum(1 for s in dim_scores if s > 0)
    if firing_dims >= 2:
        base_score = min(1.0, base_score + 0.15)

    return round(base_score, 3)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_skill_packs(
    evidence: Dict[str, Any],
    repo_context: Dict[str, Any],
    detected_deps: List[Dict[str, Any]],
) -> List[Tuple[LoadedSkill, float]]:
    """
    Score all available skill packs against repo evidence.

    Returns a list of (LoadedSkill, score) tuples for skills that score
    at or above their own confidence_threshold, sorted by score descending.

    If NO skill qualifies, triggers the SkillComposer to auto-generate
    a new skill pack tailored to this repository.
    """
    all_skills = load_all_skills()

    if not all_skills:
        print("[SKILL MATCHER] No skill packs found in packs/ directory.", file=sys.stderr)

    results: List[Tuple[LoadedSkill, float]] = []
    for skill in all_skills:
        threshold = skill.detection_signals.get("confidence_threshold", 0.6)
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            threshold = 0.6

        s = score_skill(skill, evidence, repo_context, detected_deps)
        if s >= threshold:
            results.append((skill, s))

    # Sort by score descending
    results.sort(key=lambda x: x[1], reverse=True)

    if results:
        _log_matches(results)
    else:
        # No skill matched → attempt auto-composition
        print("[SKILL MATCHER] No skill pack matched — triggering SkillComposer.", file=sys.stderr)
        try:
            from app.skills.skill_composer import compose_missing_skill
            generated = compose_missing_skill(evidence, repo_context, detected_deps)
            if generated:
                results = [(generated, 0.7)]
                print(f"[SKILL MATCHER] Auto-composed skill: {generated.id}", file=sys.stderr)
        except Exception as e:
            print(f"[SKILL MATCHER] SkillComposer failed: {e}", file=sys.stderr)

    return results


def _log_matches(results: List[Tuple[LoadedSkill, float]]) -> None:
    """Log matched skill packs to stderr for pipeline visibility."""
    ids = ", ".join(f"{s.id}({score:.2f})" for s, score in results)
    print(f"[SKILL MATCHER] Activated: {ids}", file=sys.stderr)
