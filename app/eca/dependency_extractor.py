"""
dependency_extractor.py — Phase 3 Extractor
----------------------------------------------
Extracts dependency/framework versions from build files.

Scans: build.gradle, build.gradle.kts, pom.xml, package.json, requirements.txt

Output:
  {
    "dependencies": [
      { "name": str, "current_version": str, "category": str }
    ],
    "build_tool": str,
    "language": str
  }
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Any


# ---------------------------------------------------------------------------
# Gradle patterns
# ---------------------------------------------------------------------------

# Kotlin DSL:  kotlin("jvm") version "1.9.0"  or  id("org.jetbrains.kotlin.jvm") version "1.9.0"
_GRADLE_PLUGIN_VERSION = re.compile(
    r'''(?:kotlin\s*\(\s*["'](\w+)["']\s*\)\s*version\s*["']([^"']+)["']'''
    r'''|id\s*\(\s*["']([^"']+)["']\s*\)\s*version\s*["']([^"']+)["'])''',
    re.IGNORECASE,
)

# ext.kotlin_version = "1.3.21"  or  kotlinVersion = '1.3.21'
_GRADLE_EXT_VERSION = re.compile(
    r"""(\w+)[Vv]ersion\s*=\s*["']([^"']+)["']""",
)

# implementation 'org.springframework.boot:spring-boot-starter:2.1.4.RELEASE'
# implementation("org.springframework.boot:spring-boot-starter:2.1.4.RELEASE")
_GRADLE_DEPENDENCY = re.compile(
    r"""(?:implementation|api|compile|runtimeOnly|testImplementation)\s*[\('"]\s*([^:]+):([^:]+):([^"')]+)""",
    re.IGNORECASE,
)

# sourceCompatibility = '1.8'  or  jvmTarget = '1.8'
_GRADLE_JVM = re.compile(
    r"""(?:sourceCompatibility|targetCompatibility|jvmTarget)\s*=\s*["']?([^"'\s]+)""",
    re.IGNORECASE,
)

# jcenter() detection
_JCENTER = re.compile(r'\bjcenter\s*\(\s*\)', re.IGNORECASE)

# ---------------------------------------------------------------------------
# Maven patterns
# ---------------------------------------------------------------------------

_MAVEN_GAV = re.compile(
    r'<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>\s*<version>([^<]+)</version>',
    re.DOTALL,
)

_MAVEN_PARENT_VERSION = re.compile(
    r'<parent>.*?<artifactId>([^<]+)</artifactId>.*?<version>([^<]+)</version>.*?</parent>',
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# package.json patterns
# ---------------------------------------------------------------------------

_PACKAGE_JSON_DEP = re.compile(
    r'"([^"]+)"\s*:\s*"([^"]+)"',
)


def _clean_dep_name(raw: str) -> str:
    """Strip leading/trailing quotes and whitespace from extracted dep names.

    Kotlin DSL uses  implementation("group:artifact:version")  which can
    leave a leading '"' in the captured group if the regex boundary lands
    inside the string.  This normalises names for all callers.
    """
    return raw.strip().strip('"\' \\n\\r')


def _categorize_dep(group: str, artifact: str) -> str:
    """Assign a category based on Maven group/artifact names."""
    key = f"{group}:{artifact}".lower()
    if "spring-boot" in key:
        return "framework"
    if "kotlin" in key or "jetbrains" in key:
        return "language"
    if "grpc" in key or "protobuf" in key:
        return "communication"
    if "mysql" in key or "postgres" in key or "jdbc" in key or "jpa" in key or "hibernate" in key:
        return "database"
    if "firebase" in key:
        return "auth"
    if "junit" in key or "mockito" in key or "test" in key:
        return "testing"
    if "docker" in key or "kubernetes" in key:
        return "infrastructure"
    return "library"


def extract_dependencies(repo_dir: Path | str) -> Dict[str, Any]:
    """
    Scan a repository directory for build files and extract dependency metadata.

    Returns a dict with keys: dependencies, build_tool, language, uses_jcenter.
    """
    repo_dir = Path(repo_dir)
    deps: List[Dict[str, str]] = []
    build_tool = "unknown"
    language = "unknown"
    uses_jcenter = False
    seen = set()

    def _add(name: str, version: str, category: str):
        key = (name.lower(), version)
        if key not in seen:
            seen.add(key)
            deps.append({"name": name, "current_version": version, "category": category})

    # --- Gradle ---
    gradle_files = list(repo_dir.rglob("build.gradle")) + list(repo_dir.rglob("build.gradle.kts"))
    for gf in gradle_files:
        build_tool = "gradle"
        try:
            text = gf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # jcenter detection
        if _JCENTER.search(text):
            uses_jcenter = True

        # Plugin versions
        for m in _GRADLE_PLUGIN_VERSION.finditer(text):
            kotlin_short, kv, plugin_id, pv = m.groups()
            if kotlin_short and kv:
                _add(f"kotlin-{_clean_dep_name(kotlin_short)}", _clean_dep_name(kv), "language")
                language = "kotlin"
            elif plugin_id and pv:
                short_name = _clean_dep_name(plugin_id.rsplit(".", 1)[-1])
                cat = "framework" if "spring" in plugin_id.lower() else "build"
                _add(short_name, _clean_dep_name(pv), cat)
                if "kotlin" in plugin_id.lower():
                    language = "kotlin"

        # ext { version = "..." }
        for m in _GRADLE_EXT_VERSION.finditer(text):
            vname, vval = m.groups()
            vname = _clean_dep_name(vname)
            vval  = _clean_dep_name(vval)
            cat = "language" if "kotlin" in vname.lower() else "framework"
            _add(vname, vval, cat)
            if "kotlin" in vname.lower():
                language = "kotlin"

        # Dependencies
        for m in _GRADLE_DEPENDENCY.finditer(text):
            group, artifact, version = m.groups()
            group    = _clean_dep_name(group)
            artifact = _clean_dep_name(artifact)
            version  = _clean_dep_name(version)
            _add(f"{group}:{artifact}", version, _categorize_dep(group, artifact))

        # JVM target
        for m in _GRADLE_JVM.finditer(text):
            _add("jvm-target", _clean_dep_name(m.group(1)), "language")

    # --- Maven ---
    pom_files = list(repo_dir.rglob("pom.xml"))
    for pf in pom_files:
        build_tool = build_tool if build_tool != "unknown" else "maven"
        try:
            text = pf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for m in _MAVEN_PARENT_VERSION.finditer(text):
            _add(m.group(1), m.group(2), "framework")

        for m in _MAVEN_GAV.finditer(text):
            group, artifact, version = m.groups()
            if "${" in version:
                continue  # Skip property references
            _add(f"{group}:{artifact}", version, _categorize_dep(group, artifact))

    # --- package.json ---
    pkg_files = list(repo_dir.rglob("package.json"))
    for pf in pkg_files:
        build_tool = build_tool if build_tool != "unknown" else "npm"
        language = language if language != "unknown" else "javascript"
        try:
            import json
            data = json.loads(pf.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        for section in ("dependencies", "devDependencies"):
            for name, version in data.get(section, {}).items():
                _add(name, version.lstrip("^~"), "library")

    # --- requirements.txt ---
    req_files = list(repo_dir.rglob("requirements.txt"))
    for rf in req_files:
        build_tool = build_tool if build_tool != "unknown" else "pip"
        language = language if language != "unknown" else "python"
        try:
            for line in rf.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = re.split(r"[=<>!~]+", line, maxsplit=1)
                name = parts[0].strip()
                version = parts[1].strip() if len(parts) > 1 else "unspecified"
                _add(name, version, "library")
        except Exception:
            continue

    return {
        "dependencies": deps,
        "build_tool": build_tool,
        "language": language,
        "uses_jcenter": uses_jcenter,
    }
