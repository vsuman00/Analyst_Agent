"""
skill_loader.py — Layer 3 Tool
---------------------------------
Discovers and loads all Skill Pack definitions from the packs/ directory.

Reads SKILL.md files, parses YAML frontmatter (detection_signals, nfr_emphasis,
memory_tags, brd_section_notes), and returns structured LoadedSkill objects.

Zero hardcoding — the loader does not know about any specific skill pack.
It reads everything from files.

Directory convention:
    app/skills/packs/{skill_id}/
    ├── SKILL.md           ← YAML frontmatter + Markdown instructions
    ├── scripts/           ← Optional Python CLI scripts
    │   └── extractor.py
    └── references/        ← Optional deep docs for on-demand reading
        └── patterns.md
"""

from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PACKS_DIR = Path(__file__).parent / "packs"
GENERATED_DIR = PACKS_DIR / "_generated"


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class LoadedSkill:
    """In-memory representation of a parsed SKILL.md skill pack."""
    id: str                                     # directory name (e.g. "web_api")
    name: str                                   # from YAML frontmatter
    version: str                                # from YAML frontmatter
    description: str                            # from YAML frontmatter
    detection_signals: Dict[str, Any] = field(default_factory=dict)
    nfr_emphasis: List[str] = field(default_factory=list)
    memory_tags: List[str] = field(default_factory=list)
    brd_section_notes: Dict[str, str] = field(default_factory=dict)
    skill_dir: Path = field(default_factory=lambda: Path("."))
    has_scripts: bool = False
    script_names: List[str] = field(default_factory=list)
    instructions_body: str = ""                 # Markdown body after frontmatter
    auto_generated: bool = False


# ---------------------------------------------------------------------------
# YAML Frontmatter Parser
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(
    r"\A\s*---\s*\n(.*?)\n---\s*\n?(.*)",
    re.DOTALL,
)


def _parse_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    """
    Parse YAML frontmatter delimited by --- markers at the top of a Markdown file.

    Returns (frontmatter_dict, markdown_body).
    Falls back to a simple key-value parser if PyYAML is not installed.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    yaml_block = match.group(1)
    body = match.group(2)

    if _HAS_YAML:
        try:
            fm = _yaml.safe_load(yaml_block) or {}
        except _yaml.YAMLError:
            fm = _fallback_parse(yaml_block)
    else:
        fm = _fallback_parse(yaml_block)

    return fm, body


def _fallback_parse(yaml_block: str) -> Dict[str, Any]:
    """
    Robust minimal YAML parser for environments without PyYAML.
    Handles:
      - Simple scalars (key: value)
      - Inline lists ([a, b, c])
      - Nested dicts (indentation-based)
      - Multi-line strings (>- continuation)
      - Booleans (true/false)
      - Numbers (0.5, 120, etc.)
    """
    result: Dict[str, Any] = {}
    lines = yaml_block.strip().splitlines()

    # Stack of (parent_indent, parent_dict) for tracking nesting
    # parent_indent = the indent level of the key that OWNS this dict
    stack: List[tuple] = [(-1, result)]

    i = 0
    while i < len(lines):
        raw_line = lines[i]
        stripped = raw_line.strip()
        i += 1

        # Skip empty lines and comments
        if not stripped or stripped.startswith("#"):
            continue

        # Calculate indentation
        indent = len(raw_line) - len(raw_line.lstrip())

        # Pop stack: if current indent <= parent_indent of top entry,
        # we've returned to a higher (or same) level
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()

        parent = stack[-1][1]

        if ":" not in stripped:
            continue

        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()

        if not value or value == ">-":
            if value == ">-":
                # Collect multi-line string (all following lines with greater indent)
                parts = []
                while i < len(lines):
                    next_line = lines[i]
                    next_stripped = next_line.strip()
                    next_indent = len(next_line) - len(next_line.lstrip())
                    if not next_stripped:
                        i += 1
                        continue
                    if next_indent > indent:
                        parts.append(next_stripped)
                        i += 1
                    else:
                        break
                parent[key] = " ".join(parts)
            else:
                # Nested dict — create a new child dict
                child: Dict[str, Any] = {}
                parent[key] = child
                # Push with THIS key's indent — children must have indent > this
                stack.append((indent, child))
        else:
            # Parse the value
            parent[key] = _parse_value(value)

    return result


def _parse_value(value: str) -> Any:
    """Parse a YAML scalar value into a Python type."""
    # Inline list: [a, b, c]
    if value.startswith("[") and value.endswith("]"):
        items = [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]
        return items

    # Boolean
    if value.lower() in ("true", "false"):
        return value.lower() == "true"

    # Number (float or int)
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    # Strip surrounding quotes
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]

    return value


# ---------------------------------------------------------------------------
# Skill Loader
# ---------------------------------------------------------------------------

def load_skill_from_dir(skill_dir: Path) -> Optional[LoadedSkill]:
    """
    Load a single skill pack from a directory containing a SKILL.md file.
    Returns None if SKILL.md is missing or unparseable.
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None

    try:
        content = skill_md.read_text(encoding="utf-8")
    except OSError:
        return None

    fm, body = _parse_frontmatter(content)
    if not fm:
        return None

    scripts_dir = skill_dir / "scripts"
    script_names = []
    if scripts_dir.is_dir():
        script_names = [f.name for f in scripts_dir.iterdir()
                        if f.is_file() and f.suffix == ".py"]

    return LoadedSkill(
        id=skill_dir.name,
        name=fm.get("name", skill_dir.name),
        version=str(fm.get("version", "1.0")),
        description=fm.get("description", ""),
        detection_signals=fm.get("detection_signals", {}),
        nfr_emphasis=fm.get("nfr_emphasis", []),
        memory_tags=fm.get("memory_tags", []),
        brd_section_notes=fm.get("brd_section_notes", {}),
        skill_dir=skill_dir,
        has_scripts=bool(script_names),
        script_names=script_names,
        instructions_body=body.strip(),
        auto_generated="_generated" in str(skill_dir),
    )


def load_all_skills() -> List[LoadedSkill]:
    """
    Discover and load all SKILL.md files from packs/ and packs/_generated/.

    Returns a list of LoadedSkill objects.
    Zero hardcoding — reads everything from the filesystem.
    """
    skills: List[LoadedSkill] = []

    # Scan stable packs
    if PACKS_DIR.is_dir():
        for child in sorted(PACKS_DIR.iterdir()):
            if child.is_dir() and child.name != "_generated":
                skill = load_skill_from_dir(child)
                if skill:
                    skills.append(skill)

    # Scan auto-generated packs
    if GENERATED_DIR.is_dir():
        for child in sorted(GENERATED_DIR.iterdir()):
            if child.is_dir():
                skill = load_skill_from_dir(child)
                if skill:
                    skills.append(skill)

    return skills
