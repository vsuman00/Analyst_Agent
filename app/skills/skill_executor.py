"""
skill_executor.py — Layer 3 Tool
-----------------------------------
Runs activated skill pack scripts against the cloned repository.

Execution model:
  - Each skill's SKILL.md declares available scripts in scripts/
  - Scripts are Python CLIs: python scripts/extractor.py <repo_dir> <output.json> <subcommand>
  - Output is always JSON written to a file (following the platform convention)
  - Scripts run in a subprocess with a timeout to prevent hangs
  - If a script fails, that skill is skipped — pipeline continues

This executor produces a SkillExecutionResult (Pydantic model) that is
injected into the FeatureExtractionAgent as supplementary context.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import os
from pathlib import Path
from typing import Dict, List, Any, Tuple

from app.skills.skill_loader import LoadedSkill
from app.schemas.models import SkillActivation, SkillExecutionResult


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCRIPT_TIMEOUT = 120  # seconds — generous for large repos
_PYTHON_CMD = sys.executable  # use the same Python that runs the pipeline


# ---------------------------------------------------------------------------
# Single-Script Runner
# ---------------------------------------------------------------------------

def _run_script(
    skill: LoadedSkill,
    script_name: str,
    repo_dir: str,
    subcommand: str,
) -> Dict[str, Any]:
    """
    Execute a single skill script as a subprocess.

    Convention (same as science skills):
        python scripts/{script}.py <repo_dir> <output_file> <subcommand>

    Returns parsed JSON output or empty dict on failure.
    """
    script_path = skill.skill_dir / "scripts" / script_name
    if not script_path.exists():
        print(f"[SKILL EXEC] Script not found: {script_path}", file=sys.stderr)
        return {}

    # Create a temp file for JSON output
    fd, out_file = tempfile.mkstemp(suffix=".json", prefix=f"skill_{skill.id}_")
    os.close(fd)

    cmd = [_PYTHON_CMD, str(script_path), str(repo_dir), out_file, subcommand]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_SCRIPT_TIMEOUT,
            cwd=str(Path(__file__).resolve().parent.parent.parent),  # project root
        )

        if result.returncode != 0:
            stderr_snippet = result.stderr[:300] if result.stderr else "(no stderr)"
            print(
                f"[SKILL EXEC] {skill.id}/{subcommand} exited {result.returncode}: {stderr_snippet}",
                file=sys.stderr,
            )
            return {}

        out_path = Path(out_file)
        if not out_path.exists() or out_path.stat().st_size == 0:
            print(f"[SKILL EXEC] {skill.id}/{subcommand} produced no output.", file=sys.stderr)
            return {}

        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"result": data}
        except json.JSONDecodeError as e:
            print(f"[SKILL EXEC] {skill.id}/{subcommand} invalid JSON: {e}", file=sys.stderr)
            return {}

    except subprocess.TimeoutExpired:
        print(f"[SKILL EXEC] {skill.id}/{subcommand} timed out ({_SCRIPT_TIMEOUT}s).", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"[SKILL EXEC] {skill.id}/{subcommand} error: {e}", file=sys.stderr)
        return {}
    finally:
        # Clean up temp file
        try:
            os.unlink(out_file)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Instruction Extraction (for instruction-only skills)
# ---------------------------------------------------------------------------

def _extract_instructions(skill: LoadedSkill) -> Dict[str, Any]:
    """
    For skills without scripts (instruction-only), parse the SKILL.md body
    to extract BRD section notes and NFR emphasis as structured signals.
    These are passed to the pipeline as additional_signals.
    """
    signals: Dict[str, Any] = {}

    if skill.brd_section_notes:
        signals["brd_section_notes"] = skill.brd_section_notes

    if skill.nfr_emphasis:
        signals["nfr_emphasis"] = skill.nfr_emphasis

    if skill.instructions_body:
        signals["skill_instructions"] = skill.instructions_body[:2000]

    return signals


# ---------------------------------------------------------------------------
# Subcommand Discovery
# ---------------------------------------------------------------------------

def _discover_subcommands(skill: LoadedSkill) -> List[str]:
    """
    Read the SKILL.md body to discover which subcommands are available.
    Looks for patterns like:
        scripts/extractor.py <repo_dir> <output_file> contracts
        scripts/extractor.py <repo_dir> <output_file> auth

    Falls back to ["extract"] as a default subcommand.
    """
    body = skill.instructions_body
    if not body:
        return ["extract"]

    import re
    # Match: scripts/*.py <args> <subcommand>
    # The subcommand is typically the last word on a code line
    pattern = re.compile(
        r"scripts/\w+\.py\s+\S+\s+\S+\s+(\w+)",
        re.IGNORECASE,
    )
    found = list(set(pattern.findall(body)))
    return found if found else ["extract"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def execute_skill_packs(
    activated: List[Tuple[LoadedSkill, float]],
    repo_dir: str,
) -> SkillExecutionResult:
    """
    Run all activated skill packs against the cloned repository.

    For each activated skill:
      - If it has scripts → run each discovered subcommand
      - If instruction-only → extract structured signals from SKILL.md body

    Results are aggregated into a single SkillExecutionResult.
    Individual skill failures never block the pipeline.

    Parameters:
        activated : list of (LoadedSkill, detection_score) tuples
        repo_dir  : path to the cloned repository source

    Returns:
        SkillExecutionResult with merged features, signals, and BRD hints
    """
    all_activations: List[SkillActivation] = []
    all_features: List[Dict[str, Any]] = []
    all_signals: Dict[str, Any] = {}
    all_hints: Dict[str, str] = {}

    for skill, score in activated:
        scripts_run: List[str] = []

        if skill.has_scripts and skill.script_names:
            # Script-based skill: run each subcommand
            subcommands = _discover_subcommands(skill)

            for subcmd in subcommands:
                for script_name in skill.script_names:
                    output = _run_script(skill, script_name, repo_dir, subcmd)
                    if output:
                        scripts_run.append(subcmd)

                        # Merge features if the script returned them
                        if "features" in output:
                            feats = output["features"]
                            if isinstance(feats, list):
                                all_features.extend(feats)

                        # Merge signals
                        for key, val in output.items():
                            if key != "features":
                                all_signals[f"{skill.id}.{key}"] = val
        else:
            # Instruction-only skill: extract structured signals from SKILL.md
            inst_signals = _extract_instructions(skill)
            for key, val in inst_signals.items():
                all_signals[f"{skill.id}.{key}"] = val

        # Merge BRD section hints from all activated skills
        for section_key, hint in skill.brd_section_notes.items():
            existing = all_hints.get(section_key, "")
            all_hints[section_key] = f"{existing} {hint}".strip() if existing else hint

        all_activations.append(SkillActivation(
            skill_id=skill.id,
            skill_name=skill.name,
            score=score,
            auto_generated=skill.auto_generated,
            scripts_run=scripts_run,
        ))

    result = SkillExecutionResult(
        activated_skills=all_activations,
        additional_features=all_features,
        additional_signals=all_signals,
        brd_section_hints=all_hints,
    )

    # Summary log
    total_feats = len(all_features)
    total_signals = len(all_signals)
    print(
        f"[SKILL EXEC] Executed {len(all_activations)} skill(s) → "
        f"{total_feats} features, {total_signals} signals extracted.",
        file=sys.stderr,
    )

    return result
