"""
skill_composer.py — Layer 3 Tool
-----------------------------------
Auto-generates missing skill packs via LLM when no existing pack matches.

This is the anti-hardcoding mechanism: instead of requiring a human to write
a SKILL.md + scripts for every repo type, the composer synthesises them
on-the-fly and saves them to packs/_generated/ for future reuse.

Generated skills are:
  - Functional immediately (used in the current pipeline run)
  - Persisted to disk (reused for similar repos in future runs)
  - Tagged auto_generated=True (distinguishable from curated packs)
  - Idempotent (same evidence fingerprint → same skill_id → no duplicates)

Follows the same YAML frontmatter + scripts pattern as curated packs.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

from app.skills.skill_loader import LoadedSkill, load_skill_from_dir, GENERATED_DIR


# ---------------------------------------------------------------------------
# Composer System Prompt
# ---------------------------------------------------------------------------

COMPOSER_SYSTEM_PROMPT = """\
You are an expert software analyst creating a Skill Pack definition for a BRD \
generation pipeline. A Skill Pack helps the pipeline extract domain-specific \
signals (features, patterns, API contracts) from a software repository.

A Skill Pack consists of:
1. A SKILL.md file (with YAML frontmatter defining detection signals + Markdown instructions)
2. An optional Python CLI script (scripts/extractor.py) for code-level extraction

YAML FRONTMATTER SCHEMA — must match exactly:
---
name: {skill-id-kebab-case}
version: "1.0"
description: >-
  {One paragraph: what this pack analyses, when it should activate. Max 300 chars.}

detection_signals:
  evidence_flags: [{list of evidence dict boolean keys that trigger this, e.g. has_http_api}]
  dependency_keywords: [{package/library names, e.g. fastapi, express}]
  file_patterns: [{glob patterns, e.g. "**/routes/**", "*.proto"}]
  confidence_threshold: 0.5

nfr_emphasis: [{NFR category keywords to emphasise, e.g. latency_p99}]
memory_tags: [{tags for indexing, e.g. api_design, rest_patterns}]
brd_section_notes:
  section_5: "{hint for functional requirements section}"
  section_8: "{hint for tech stack section}"
---

PYTHON SCRIPT RULES (for scripts/extractor.py):
- Accept 3 positional args: <repo_dir> <output_file> <subcommand>
- Use argparse with subcommands
- Write JSON output to file, short status to stdout
- Use ONLY stdlib (pathlib, ast, re, json, os, sys) — NO pip installs
- Handle errors gracefully, exit code 1 on failure
- The script analyses the FILES in repo_dir to extract domain-specific signals

STRICT RULES:
- Do NOT invent signals not grounded in the provided evidence
- detection_signals MUST use real field names from the evidence dict
- The script MUST be functional Python that can be executed immediately
- If no meaningful extraction script can be written, set script_content to null

Return ONLY valid JSON:
{
  "skill_id": "unique-kebab-case-id",
  "skill_md_content": "full SKILL.md text including --- frontmatter ---",
  "script_content": "full Python script text OR null if instruction-only",
  "rationale": "one sentence: why this skill pack was generated"
}
"""


# ---------------------------------------------------------------------------
# Evidence Fingerprinting (for idempotency)
# ---------------------------------------------------------------------------

def _evidence_fingerprint(evidence: Dict, repo_context: Dict) -> str:
    """
    Generate a short deterministic hash from the most distinctive evidence
    signals so that the same repo type always produces the same skill_id.
    """
    key_signals = {
        "platform": evidence.get("platform", "unknown"),
        "primary_language": evidence.get("primary_language", "unknown"),
        "has_http_api": evidence.get("has_http_api", False),
        "has_grpc": evidence.get("has_grpc", False),
        "has_android": evidence.get("has_android", False),
        "has_ios": evidence.get("has_ios", False),
        "has_database": evidence.get("has_database", False),
        "build_tool": evidence.get("build_tool", "unknown"),
        "tech_framework": _dominant_framework(repo_context),
    }
    raw = json.dumps(key_signals, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()[:8]


def _dominant_framework(repo_context: Dict) -> str:
    """Extract the most prominent framework from tech_stack, if any."""
    tech = repo_context.get("tech_stack", {})
    if isinstance(tech, dict):
        fw = tech.get("framework", tech.get("frameworks", ""))
        if isinstance(fw, list):
            return fw[0] if fw else ""
        return str(fw)
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compose_missing_skill(
    evidence: Dict[str, Any],
    repo_context: Dict[str, Any],
    detected_deps: List[Dict[str, Any]],
) -> Optional[LoadedSkill]:
    """
    Use LLM to generate a new skill pack tailored to the repository signals.

    Saves the result to packs/_generated/{skill_id}/ for future reuse.
    If a skill with the same evidence fingerprint already exists, loads it
    instead of regenerating (idempotency).

    Returns the LoadedSkill or None on failure.
    """
    # Check if OPENAI_API_KEY is available
    if not os.environ.get("OPENAI_API_KEY"):
        print("[SKILL COMPOSER] No API key — cannot auto-compose.", file=sys.stderr)
        return None

    try:
        from app.utils.llm_client import llm_json_call
    except ImportError:
        print("[SKILL COMPOSER] LLM client unavailable.", file=sys.stderr)
        return None

    # Check for existing generated skill with same fingerprint
    fingerprint = _evidence_fingerprint(evidence, repo_context)

    # Search _generated/ for existing match
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    for child in GENERATED_DIR.iterdir():
        if child.is_dir() and fingerprint in child.name:
            existing = load_skill_from_dir(child)
            if existing:
                print(
                    f"[SKILL COMPOSER] Reusing existing generated skill: {existing.id}",
                    file=sys.stderr,
                )
                return existing

    # Build the LLM prompt with repo context
    dep_names = []
    for d in detected_deps[:20]:
        if isinstance(d, dict):
            dep_names.append(d.get("name", ""))
        elif isinstance(d, str):
            dep_names.append(d)

    readme_excerpt = ""
    intent = repo_context.get("intent_signals", {})
    if isinstance(intent, dict):
        readme_excerpt = intent.get("readme", "")[:500]

    user_prompt = (
        "Repository signals for which no existing skill pack matched:\n\n"
        f"Evidence flags:\n{json.dumps({k: v for k, v in evidence.items() if isinstance(v, bool)}, indent=2)}\n\n"
        f"Platform: {evidence.get('platform', 'unknown')}\n"
        f"Primary Language: {evidence.get('primary_language', 'unknown')}\n"
        f"Build Tool: {evidence.get('build_tool', 'unknown')}\n"
        f"Tech Stack: {json.dumps(repo_context.get('tech_stack', {}), indent=2)}\n"
        f"Top Dependencies: {dep_names}\n"
        f"README Excerpt: {readme_excerpt}\n\n"
        f"Evidence fingerprint: {fingerprint}\n\n"
        "Generate a skill pack tailored to this specific repository type."
    )

    try:
        result = llm_json_call(COMPOSER_SYSTEM_PROMPT, user_prompt, max_tokens=2000)
    except Exception as e:
        print(f"[SKILL COMPOSER] LLM call failed: {e}", file=sys.stderr)
        return None

    skill_id = result.get("skill_id", f"auto_{fingerprint}")
    # Ensure the fingerprint is in the directory name for idempotency
    dir_name = f"{skill_id}_{fingerprint}" if fingerprint not in skill_id else skill_id
    skill_md_content = result.get("skill_md_content", "")
    script_content = result.get("script_content")
    rationale = result.get("rationale", "Auto-composed by SkillComposer")

    if not skill_md_content:
        print("[SKILL COMPOSER] LLM returned empty SKILL.md content.", file=sys.stderr)
        return None

    # Save to _generated/
    gen_dir = GENERATED_DIR / dir_name
    gen_dir.mkdir(parents=True, exist_ok=True)

    (gen_dir / "SKILL.md").write_text(skill_md_content, encoding="utf-8")

    if script_content:
        scripts_dir = gen_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        (scripts_dir / "extractor.py").write_text(script_content, encoding="utf-8")

    print(f"[SKILL COMPOSER] ✅ Generated skill pack: {dir_name}", file=sys.stderr)
    print(f"[SKILL COMPOSER] Rationale: {rationale}", file=sys.stderr)
    print(f"[SKILL COMPOSER] Saved to: {gen_dir}", file=sys.stderr)

    # Load and return the just-saved skill
    loaded = load_skill_from_dir(gen_dir)
    return loaded
