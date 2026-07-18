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
# Tech Stack Detection — evidence-driven, fully generic
# ---------------------------------------------------------------------------

# Human-readable purpose labels for well-known dep name fragments.
# This is a DISPLAY HINT only — not a detection mechanism.
# Add entries here when you want a friendlier description in the BRD table.
# Keys are lowercase substrings of dep names or category values.
_TECH_PURPOSES: Dict[str, str] = {
    # Languages / runtimes
    "kotlin":          "Primary programming language",
    "python":          "Primary programming language",
    "javascript":      "Primary programming language",
    "typescript":      "Typed superset of JavaScript",
    "java":            "Primary programming language",
    "go":              "Primary programming language",
    "scala":           "Functional/OO language on the JVM",
    "rust":            "Systems-level language",
    "swift":           "Primary programming language (iOS/macOS)",
    "ruby":            "Primary programming language",
    "csharp":          "Primary programming language (.NET)",
    # Build tools
    "gradle":          "Build automation and dependency management",
    "maven":           "Build automation and dependency management",
    "npm":             "Package manager for JavaScript",
    "pip":             "Package manager for Python",
    "cargo":           "Package manager for Rust",
    # Platforms
    "android":         "Target mobile platform",
    "ios":             "Target mobile platform",
    "web":             "Target web platform",
    "desktop":         "Target desktop platform",
    "server":          "Server-side / backend platform",
    # Infra
    "docker":          "Containerisation — packages the app for consistent deployment",
    "kubernetes":      "Container orchestration — manages deployment at scale",
    # Common framework fragments (dep name substrings)
    "spring":          "Java/Kotlin web application framework",
    "react":           "User interface library",
    "angular":         "Frontend application framework",
    "vue":             "Frontend application framework",
    "django":          "Python web framework",
    "flask":           "Lightweight Python web framework",
    "fastapi":         "High-performance Python API framework",
    "express":         "Node.js web framework",
    "next":            "React-based full-stack framework",
    "compose":         "Declarative UI toolkit",
    "retrofit":        "Type-safe HTTP client",
    "okhttp":          "HTTP networking library",
    "ktor":            "Asynchronous framework for Kotlin",
    "coroutines":      "Asynchronous/concurrent programming library",
    "serialization":   "Data serialisation library",
    "hilt":            "Dependency injection framework",
    "room":            "Android local database library",
    "realm":           "Mobile-first database",
    "postgres":        "Relational database",
    "mysql":           "Relational database",
    "mongo":           "Document-oriented database",
    "redis":           "In-memory cache / data store",
    "sqlite":          "Embedded relational database",
    "kafka":           "Distributed message streaming platform",
    "rabbitmq":        "Message broker",
    "grpc":            "High-performance RPC framework",
    "graphql":         "Query language for APIs",
    "openai":          "AI/LLM integration",
    "langchain":       "LLM orchestration framework",
    "tensorflow":      "Machine learning framework",
    "pytorch":         "Machine learning framework",
    "junit":           "Unit testing framework",
    "pytest":          "Python testing framework",
    "jest":          "JavaScript testing framework",
}


def _purpose_for(tech_name: str) -> str:
    """Return a human-readable purpose string for a technology name.

    Looks for any key in _TECH_PURPOSES that appears as a substring of
    the lowercased name.  Falls back to 'Supporting technology component'.
    """
    name_lower = tech_name.lower()
    for fragment, purpose in _TECH_PURPOSES.items():
        # Use word-boundary style match: fragment must be a whole word or
        # appear at a token boundary to avoid 'r' matching 'Gradle', etc.
        import re as _re
        if _re.search(r'(?<![a-z])' + _re.escape(fragment) + r'(?![a-z])', name_lower):
            return purpose
    return "Supporting technology component"


def _build_tech_stack_from_evidence(
    dep_data: Dict[str, Any],
    evidence: Dict[str, Any],
) -> Dict[str, str]:
    """Build a human-readable tech stack dict from already-extracted evidence.

    This is the single authoritative source for tech_stack.  It consumes
    the outputs of dependency_extractor and evidence_manifest — both of
    which work generically across all build systems (Gradle, Maven, npm,
    pip, Cargo, Go modules, etc.).

    NO hardcoded language patterns live here.  Everything is derived from
    what the extractors already found.
    """
    stack: Dict[str, str] = {}

    # 1. Primary language — dependency_extractor sets this for every build system
    lang = dep_data.get("language", "unknown")
    if lang and lang != "unknown":
        stack["language"] = lang.title()   # "kotlin" → "Kotlin"

    # 2. Build tool — gradle, maven, npm, pip, unknown
    build_tool = dep_data.get("build_tool", "unknown")
    if build_tool and build_tool != "unknown":
        stack["build_tool"] = build_tool.title()

    # 3. Deployment platform — from evidence manifest
    platform = evidence.get("platform", "unknown")
    if platform and platform not in ("unknown", "library"):
        stack["platform"] = platform.title()

    # 4. Infra signals — evidence manifest file-system scan
    if evidence.get("has_docker"):
        stack["containerization"] = "Docker"
    if evidence.get("has_kubernetes"):
        stack["orchestration"] = "Kubernetes"

    # 5. Key framework/library deps — use the cleaned names from dependency_extractor.
    #    We pick deps categorised as 'framework' or 'language' (non-build, non-test).
    #    Limit to 8 entries so the BRD table stays readable.
    import re as _re
    skip_cats  = {"testing", "build"}
    skip_names = {"jvm-target", "application", "android", "serialization"}
    seen_labels: Set[str] = set()
    dep_count = 0
    for dep in dep_data.get("dependencies", []):
        if dep_count >= 8:
            break
        cat  = dep.get("category", "")
        name = dep.get("name", "").strip()
        if cat in skip_cats:
            continue
        # Strip Maven/Gradle group prefix for display
        display = name.split(":")[-1].strip() if ":" in name else name
        # Aggressively strip any quote/whitespace/newline artifacts from the regex parser
        display = _re.split(r'[\n\r"\\]', display)[0].strip().strip("' ")
        if not display or display.lower() in skip_names:
            continue
        if display.lower() in seen_labels:
            continue

        seen_labels.add(display.lower())
        stack[f"dep_{dep_count}"] = display
        dep_count += 1

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
    dep_data: Optional[Dict[str, Any]] = None,
    evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build the full RepoContext from a cloned repo directory and chunk data.

    Parameters
    ----------
    repo_root_str : str
        Absolute or relative path to the cloned repository root.
    chunks_data : dict
        Output of content_processor.run_content_processor() — {"chunks": [...]}
    dep_data : dict, optional
        Output of dependency_extractor.extract_dependencies().  When supplied,
        tech_stack is built from the actual extracted deps rather than from
        heuristic file-extension scanning.  Strongly recommended.
    evidence : dict, optional
        Output of evidence_manifest.build_evidence_manifest().  Provides
        platform, Docker, Kubernetes and other infrastructure signals.

    Returns
    -------
    dict matching the RepoContext schema documented at the top of this file.
    """
    repo_root = Path(repo_root_str)
    repo_name = repo_root.name

    # 1. Intent signals (priority waterfall)
    intent_signals = build_intent_signals(repo_root)
    intent_signals.pop("_pkg_raw", None)  # no longer needed — dep_data is the source

    # 2. Tech stack — use evidence-driven builder when dep_data is available,
    #    otherwise produce an empty dict (caller should supply dep_data).
    tech_stack = _build_tech_stack_from_evidence(
        dep_data  or {},
        evidence  or {},
    )

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
        "repo_name":         repo_name,
        "intent_signals":    intent_signals,
        "tech_stack":        tech_stack,
        "structure":         structure,
        "key_file_snippets": key_snippets,
        "no_readme":         no_readme,
        "confidence_note":   confidence_note,
    }

    print(f"[RepoContextBuilder] Built context for '{repo_name}':")
    print(f"  README source : {intent_signals.get('source', 'none')}")
    print(f"  Tech stack    : {list(tech_stack.values())}")
    print(f"  Routes        : {len(structure['routes'])} files")
    print(f"  Components    : {len(structure['components'])} files")
    print(f"  Key snippets  : {len(key_snippets)} selected")

    return context
