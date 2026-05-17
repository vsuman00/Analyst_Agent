"""
repo_context_builder.py — Layer 3 Tool
----------------------------------------
RepoContextBuilder

Produces a single, rich, PRIORITIZED context JSON from a cloned repository.
This is the LLM's PRIMARY input — replacing the lossy aggregate→normalize chain.

OUTPUT SCHEMA:
{
  "repo_name": str,
  "intent_signals": {
    "readme": str,            # Full README text (up to 4000 chars). Empty if none found.
    "package_description": str,
    "package_keywords": [str],
    "package_name": str,
    "source": str             # Which tier provided the readme signal
  },
  "tech_stack": {str: str},   # {"framework": "React 19", "language": "TypeScript", ...}
  "structure": {
    "routes":     [str],      # File names from routes/, pages/, views/
    "components": [str],      # File names from components/, ui/
    "constants":  [str],      # File names from constants/, config/ (non-env)
    "types":      [str],      # File names from types/, models/, schemas/
    "services":   [str],      # File names from services/, utils/, lib/
  },
  "key_file_snippets": [
    {"file": str, "reason": str, "content": str}
  ],
  "no_readme": bool,
  "confidence_note": str
}

INTENT SIGNAL WATERFALL (in priority order):
  1. README.md / README.rst / README.txt / readme.md (up to 4000 chars)
  2. package.json  "description" + "keywords" + "name"
  3. pyproject.toml [tool.poetry] or [project] description
  4. Cargo.toml [package] description
  5. go.mod module name + top-level .go file comment
  6. Top-level docstring of main.py / app.py / index.ts / server.js
  7. [NO_DOCUMENTATION] — signals LLM to lower confidence

NO HARDCODED DOMAIN KEYWORDS. Everything is structural and content-based.
"""

from __future__ import annotations

import json
import re
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

# Dynamic language registry — all extension knowledge lives in language_registry.json
from app.eca.language_loader import (
    _build_ext_to_language,   # ext → language_name map
    _load_registry,           # full registry dict
    is_binary,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

README_NAMES = [
    "README.md", "readme.md", "README.rst", "readme.rst",
    "README.txt", "readme.txt", "README", "readme",
]

MANIFEST_NAMES = [
    "package.json", "pyproject.toml", "Cargo.toml",
    "go.mod", "pom.xml", "build.gradle",
]

ENTRY_POINT_NAMES = [
    "main.py", "app.py", "server.py", "index.py",
    "index.ts", "index.tsx", "main.ts", "main.tsx",
    "server.js", "index.js", "app.js",
    "main.go",
]

# Directory names that indicate specific structural roles
ROUTE_DIRS    = {"routes", "route", "pages", "page", "views", "view", "controllers", "api"}
COMPONENT_DIRS = {"components", "component", "ui", "widgets", "atoms", "molecules"}
CONSTANT_DIRS  = {"constants", "constant", "consts", "config", "configs"}
TYPE_DIRS      = {"types", "type", "models", "model", "schemas", "schema", "entities", "interfaces"}
SERVICE_DIRS   = {"services", "service", "utils", "util", "lib", "helpers", "hooks", "store"}

# Files in these dirs are high-priority snippets (business logic)
BUSINESS_LOGIC_PATTERNS = re.compile(
    r"(scor|rule|validat|pric|fee|tax|discount|policy|workflow|engine|"
    r"calculat|analyz|analys|classif|rank|weight|threshold|constant|schema)",
    re.IGNORECASE,
)

# Max chars for different content types
README_MAX_CHARS     = 4000
SNIPPET_MAX_CHARS    = 600
DOCSTRING_MAX_CHARS  = 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_file_safe(path: Path, max_chars: int = 0) -> str:
    """Read a file as text safely. Returns empty string on any error."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if max_chars > 0:
            text = text[:max_chars]
        return text
    except Exception:
        return ""


def _find_file(repo_root: Path, candidates: List[str]) -> Optional[Path]:
    """Find the first existing file from a list of candidate names in repo root."""
    for name in candidates:
        p = repo_root / name
        if p.exists() and p.is_file():
            return p
    return None


def _extract_top_docstring(content: str, max_chars: int = DOCSTRING_MAX_CHARS) -> str:
    """Extract the first docstring or block comment from a source file."""
    # Python docstring
    m = re.search(r'^\s*"""(.*?)"""', content, re.DOTALL)
    if m:
        return m.group(1).strip()[:max_chars]
    m = re.search(r"^\s*'''(.*?)'''", content, re.DOTALL)
    if m:
        return m.group(1).strip()[:max_chars]
    # JS/TS block comment
    m = re.search(r'/\*\*(.*?)\*/', content, re.DOTALL)
    if m:
        return m.group(1).strip()[:max_chars]
    # Single line comments at top
    lines = [l.lstrip("/ #*").strip() for l in content.splitlines()[:10] if l.strip().startswith(("/", "#", "*"))]
    return " ".join(lines)[:max_chars]


# ---------------------------------------------------------------------------
# Intent Signal Extraction (Priority Waterfall)
# ---------------------------------------------------------------------------

def _extract_readme(repo_root: Path) -> Dict[str, str]:
    """Tier 1: Look for a README file in any common format."""
    readme_path = _find_file(repo_root, README_NAMES)
    if readme_path:
        content = _read_file_safe(readme_path, README_MAX_CHARS)
        if content.strip():
            return {
                "readme": content,
                "source": readme_path.name,
            }
    return {}


def _extract_package_json(repo_root: Path) -> Dict[str, Any]:
    """Tier 2a: Extract description, keywords, name from package.json."""
    p = repo_root / "package.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {
            "package_name":        data.get("name", ""),
            "package_description": data.get("description", ""),
            "package_keywords":    data.get("keywords", []),
            "dependencies":        list(data.get("dependencies", {}).keys()),
            "dev_dependencies":    list(data.get("devDependencies", {}).keys()),
            "scripts":             data.get("scripts", {}),
        }
    except Exception:
        return {}


def _extract_pyproject(repo_root: Path) -> Dict[str, Any]:
    """Tier 2b: Extract description from pyproject.toml."""
    p = repo_root / "pyproject.toml"
    if not p.exists():
        return {}
    content = _read_file_safe(p, 2000)
    name = re.search(r'name\s*=\s*"([^"]+)"', content)
    desc = re.search(r'description\s*=\s*"([^"]+)"', content)
    return {
        "package_name":        name.group(1) if name else "",
        "package_description": desc.group(1) if desc else "",
        "package_keywords":    [],
    }


def _extract_cargo(repo_root: Path) -> Dict[str, Any]:
    """Tier 2c: Extract description from Cargo.toml."""
    p = repo_root / "Cargo.toml"
    if not p.exists():
        return {}
    content = _read_file_safe(p, 1000)
    name = re.search(r'name\s*=\s*"([^"]+)"', content)
    desc = re.search(r'description\s*=\s*"([^"]+)"', content)
    return {
        "package_name":        name.group(1) if name else "",
        "package_description": desc.group(1) if desc else "",
        "package_keywords":    [],
    }


def _extract_entry_point_docstring(repo_root: Path) -> str:
    """Tier 3: Extract top docstring from a known entry point file."""
    ep = _find_file(repo_root, ENTRY_POINT_NAMES)
    if ep:
        content = _read_file_safe(ep, 2000)
        return _extract_top_docstring(content)
    return ""


def build_intent_signals(repo_root: Path) -> Dict[str, Any]:
    """
    Run the priority waterfall and return intent_signals dict.
    Always returns a dict; never raises.
    """
    signals: Dict[str, Any] = {
        "readme": "",
        "package_name": "",
        "package_description": "",
        "package_keywords": [],
        "source": "none",
    }

    # Tier 1: README
    readme_result = _extract_readme(repo_root)
    if readme_result:
        signals["readme"] = readme_result["readme"]
        signals["source"] = readme_result["source"]

    # Tier 2: Package manifest (always extract even if README present — tech stack needs it)
    pkg_data = (
        _extract_package_json(repo_root)
        or _extract_pyproject(repo_root)
        or _extract_cargo(repo_root)
    )
    if pkg_data:
        signals["package_name"]        = pkg_data.get("package_name", "")
        signals["package_description"] = pkg_data.get("package_description", "")
        signals["package_keywords"]    = pkg_data.get("package_keywords", [])
        signals["_pkg_raw"]            = pkg_data  # used internally for tech_stack

    # Tier 3: Entry point docstring (supplement readme if readme is empty)
    if not signals["readme"]:
        docstring = _extract_entry_point_docstring(repo_root)
        if docstring:
            signals["readme"] = f"[Extracted from entry point]\n{docstring}"
            signals["source"] = "entry_point_docstring"

    return signals


# ---------------------------------------------------------------------------
# Tech Stack Detection (deterministic, from package.json deps)
# ---------------------------------------------------------------------------

# Maps dependency name patterns to human-readable tech stack labels
_TECH_PATTERNS: List[tuple[re.Pattern, str, str]] = [
    # (pattern, key, label)
    (re.compile(r"^react$"),                           "framework",        "React"),
    (re.compile(r"^next$"),                            "framework",        "Next.js"),
    (re.compile(r"^vue$"),                             "framework",        "Vue.js"),
    (re.compile(r"^@angular/core$"),                   "framework",        "Angular"),
    (re.compile(r"^svelte$"),                          "framework",        "Svelte"),
    (re.compile(r"^react-router"),                     "routing",          "React Router"),
    (re.compile(r"^@tanstack/react-router"),           "routing",          "TanStack Router"),
    (re.compile(r"^tailwindcss$"),                     "styling",          "TailwindCSS"),
    (re.compile(r"^styled-components$"),               "styling",          "Styled Components"),
    (re.compile(r"^zustand$"),                         "state_management", "Zustand"),
    (re.compile(r"^redux$|^@reduxjs/toolkit$"),        "state_management", "Redux"),
    (re.compile(r"^recoil$"),                          "state_management", "Recoil"),
    (re.compile(r"^jotai$"),                           "state_management", "Jotai"),
    (re.compile(r"^vite$"),                            "build_tool",       "Vite"),
    (re.compile(r"^typescript$"),                      "language",         "TypeScript"),
    (re.compile(r"^pdfjs-dist$|^react-pdf$"),          "libraries",        "PDF.js"),
    (re.compile(r"^react-dropzone$"),                  "libraries",        "React Dropzone"),
    (re.compile(r"^axios$|^node-fetch$|^swr$"),        "data_fetching",    "HTTP Client"),
    (re.compile(r"^prisma$"),                          "orm",              "Prisma"),
    (re.compile(r"^typeorm$"),                         "orm",              "TypeORM"),
    (re.compile(r"^mongoose$"),                        "orm",              "Mongoose"),
    (re.compile(r"^express$"),                         "server",           "Express"),
    (re.compile(r"^fastapi$"),                         "server",           "FastAPI"),
    (re.compile(r"^django$"),                          "server",           "Django"),
    (re.compile(r"^flask$"),                           "server",           "Flask"),
    (re.compile(r"^openai$"),                          "ai",               "OpenAI"),
    (re.compile(r"^langchain"),                        "ai",               "LangChain"),
    (re.compile(r"^socket\.io$|^ws$"),                 "realtime",         "WebSockets"),
    (re.compile(r"^jest$|^vitest$|^pytest$"),          "testing",          "Test Framework"),
    (re.compile(r"^docker$|^Dockerfile$"),             "infra",            "Docker"),
]


def _detect_tech_stack(pkg_raw: Dict[str, Any], repo_root: Path) -> Dict[str, str]:
    """Derive a human-readable tech stack from package manifest dependencies.

    Falls back to file-extension scanning via language_registry.json when no
    package manager manifest is present (e.g. PowerBuilder, COBOL, ABAP repos).
    """
    stack: Dict[str, str] = {}

    all_deps = (
        list(pkg_raw.get("dependencies", []))
        + list(pkg_raw.get("dev_dependencies", []))
    )

    for dep in all_deps:
        for pattern, key, label in _TECH_PATTERNS:
            if pattern.match(dep):
                if key not in stack:
                    stack[key] = label
                elif label not in stack[key]:
                    stack[key] = f"{stack[key]}, {label}"
                break

    # ── Language detection from file extensions ───────────────────────────────
    # Priority order: TypeScript > Python > Go > Rust > Java (web/backend first)
    # then fall through to registry-based detection for all other languages.
    if "language" not in stack:
        if any(repo_root.rglob("*.ts")) or any(repo_root.rglob("*.tsx")):
            stack["language"] = "TypeScript"
        elif any(repo_root.rglob("*.py")):
            stack["language"] = "Python"
        elif any(repo_root.rglob("*.go")):
            stack["language"] = "Go"
        elif any(repo_root.rglob("*.rs")):
            stack["language"] = "Rust"
        elif any(repo_root.rglob("*.java")):
            stack["language"] = "Java"
        else:
            # ── Registry-based fallback for non-web languages ─────────────────
            # Iterate over every language in the registry and check whether any
            # of its build_files exist in the repo root.  This catches
            # PowerBuilder (.pbw/.pbt), COBOL (.cbl), ABAP (.abap), etc.
            # without a single hardcoded extension here.
            reg = _load_registry()
            for lang_name, lang_def in reg.get("languages", {}).items():
                build_files = lang_def.get("build_files", [])
                found = any(
                    (repo_root / bf).exists() or bool(list(repo_root.glob(f"**/*{bf}")))
                    for bf in build_files
                    if bf  # skip empty strings
                )
                if found:
                    # Use the language's human-readable notes as the display label
                    notes = lang_def.get("notes", lang_name)
                    # Extract just the first segment before " — " for brevity
                    display = notes.split(" — ")[0].strip() if " — " in notes else lang_name.title()
                    stack["language"] = display
                    # Add framework hint if the notes carry one
                    if " — " in notes:
                        stack["platform"] = notes.split(" — ", 1)[1].strip()
                    break

    # Detect versions from package.json
    pkg_deps_with_versions = {}
    p = repo_root / "package.json"
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            pkg_deps_with_versions = {**raw.get("dependencies", {}), **raw.get("devDependencies", {})}
        except Exception:
            pass

    for key, label in list(stack.items()):
        # Try to find version for main labels
        clean_label = label.split(",")[0].strip().lower()
        for dep_name, version in pkg_deps_with_versions.items():
            if clean_label in dep_name.lower():
                version = version.lstrip("^~>=")
                stack[key] = f"{label} {version}"
                break

    return stack


# ---------------------------------------------------------------------------
# Structure Extraction
# ---------------------------------------------------------------------------

def _get_source_extensions() -> Set[str]:
    """
    Build the set of all source-file extensions registered in language_registry.json.
    Excludes extensions that are universally binary or config/doc-only.
    This is cached implicitly via language_loader's lru_cache on _build_ext_to_language.
    """
    ext_map = _build_ext_to_language()   # {'.py': 'python', '.pbl': 'powerbuilder', ...}
    return set(ext_map.keys())


def _group_files_by_role(repo_root: Path) -> Dict[str, List[str]]:
    """
    Walk the repo and group files by structural role (routes, components, etc.).
    Returns ONLY file names (not full paths) for readability in the LLM prompt.

    The source-file allowlist is derived DYNAMICALLY from language_registry.json via
    language_loader, so every registered language (Python, PowerBuilder, COBOL, ABAP,
    VB6, etc.) is automatically included — zero hardcoded extension lists.
    """
    structure: Dict[str, List[str]] = {
        "routes":     [],
        "components": [],
        "constants":  [],
        "types":      [],
        "services":   [],
    }

    skip_dirs = {".git", "node_modules", "__pycache__", ".idea", ".vscode",
                 "dist", "build", ".next", "out"}

    # All source extensions from the registry (excludes binaries, config, docs)
    source_exts = _get_source_extensions()

    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        root_path = Path(root)
        rel_parts = set(p.lower() for p in root_path.relative_to(repo_root).parts)

        for f in files:
            fname = f.lower()
            ext = Path(fname).suffix

            # Skip non-source files (binary, config-only, doc-only, or unregistered)
            if ext not in source_exts or is_binary(ext):
                continue

            if rel_parts & ROUTE_DIRS:
                structure["routes"].append(f)
            elif rel_parts & COMPONENT_DIRS:
                structure["components"].append(f)
            elif rel_parts & CONSTANT_DIRS:
                structure["constants"].append(f)
            elif rel_parts & TYPE_DIRS:
                structure["types"].append(f)
            elif rel_parts & SERVICE_DIRS:
                structure["services"].append(f)

    # Deduplicate and sort
    return {k: sorted(set(v)) for k, v in structure.items()}


# ---------------------------------------------------------------------------
# Key File Snippet Selection
# ---------------------------------------------------------------------------

def _select_key_snippets(
    repo_root: Path,
    chunks_data: Dict[str, Any],
) -> List[Dict[str, str]]:
    """
    Select the most business-relevant file snippets to include in the context.

    Priority:
      1. Files matching BUSINESS_LOGIC_PATTERNS (scoring, rules, validation, etc.)
      2. Entry point files (routes, main files)
      3. Type/model definition files

    Each snippet is capped at SNIPPET_MAX_CHARS.
    Max 10 snippets total to keep context focused.
    """
    selected: List[Dict[str, str]] = []
    seen_files: set = set()

    chunks = chunks_data.get("chunks", [])

    def _add_snippet(chunk: Dict, reason: str) -> None:
        fp = chunk.get("file_path", "")
        if fp in seen_files:
            return
        content = chunk.get("content", "")[:SNIPPET_MAX_CHARS].replace("\n", " ").strip()
        if content:
            selected.append({"file": fp, "reason": reason, "content": content})
            seen_files.add(fp)

    # Pass 1: Business logic files
    for chunk in chunks:
        if len(selected) >= 6:
            break
        fp = chunk.get("file_path", "")
        if BUSINESS_LOGIC_PATTERNS.search(fp):
            _add_snippet(chunk, "business_logic")

    # Pass 2: Entry points (routes, top-level main files)
    for chunk in chunks:
        if len(selected) >= 8:
            break
        fp = chunk.get("file_path", "").lower()
        cat = chunk.get("category", "")
        if cat in ("route", "entry_point") or any(ep in fp for ep in ["index.tsx", "main.py", "app.py", "index.ts"]):
            _add_snippet(chunk, "entry_point")

    # Pass 3: Type/model files
    for chunk in chunks:
        if len(selected) >= 10:
            break
        fp = chunk.get("file_path", "").lower()
        if any(d in fp for d in ["/types/", "/models/", "/schemas/", "/interfaces/"]):
            _add_snippet(chunk, "data_model")

    return selected


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_repo_context(
    repo_root_str: str,
    chunks_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the full RepoContext from a cloned repo directory and chunk data.

    Parameters
    ----------
    repo_root_str : str
        Absolute or relative path to the cloned repository root.
    chunks_data : dict
        Output of content_processor.run_content_processor() — {"chunks": [...]}

    Returns
    -------
    dict matching the RepoContext schema documented at the top of this file.
    """
    repo_root = Path(repo_root_str)
    repo_name = repo_root.name

    # 1. Intent signals (priority waterfall)
    intent_signals = build_intent_signals(repo_root)

    # 2. Tech stack
    pkg_raw = intent_signals.pop("_pkg_raw", {})
    tech_stack = _detect_tech_stack(pkg_raw, repo_root)

    # 3. File structure
    structure = _group_files_by_role(repo_root)

    # 4. Key file snippets
    key_snippets = _select_key_snippets(repo_root, chunks_data)

    # 5. Confidence note
    no_readme = not bool(intent_signals.get("readme", "").strip())
    if no_readme and not intent_signals.get("package_description"):
        confidence_note = "[NO_DOCUMENTATION] No README or package description found. Infer from structure only. Assign lower confidence to all features."
    elif no_readme:
        confidence_note = f"No README found. Context derived from package manifest: '{intent_signals.get('package_description', '')}'"
    else:
        confidence_note = f"README present (source: {intent_signals.get('source', 'README')}) — high confidence context."

    context = {
        "repo_name":       repo_name,
        "intent_signals":  intent_signals,
        "tech_stack":      tech_stack,
        "structure":       structure,
        "key_file_snippets": key_snippets,
        "no_readme":       no_readme,
        "confidence_note": confidence_note,
    }

    print(f"[RepoContextBuilder] Built context for '{repo_name}':")
    print(f"  README source : {intent_signals.get('source', 'none')}")
    print(f"  Tech stack    : {list(tech_stack.keys())}")
    print(f"  Routes        : {len(structure['routes'])} files")
    print(f"  Components    : {len(structure['components'])} files")
    print(f"  Key snippets  : {len(key_snippets)} selected")

    return context
