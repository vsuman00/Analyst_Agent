"""
evidence_manifest.py — ECA Layer 3 Tool
-----------------------------------------
Assembles the RepoEvidenceManifest by reading actual repo files.

This module is the single source of truth for what a repo ACTUALLY contains.
Every downstream stage (BRD composer, archetype detector, validator) queries
this manifest to decide what to write — eliminating hardcoded domain rules.

Input:
  - repo_dir     : Path — cloned repository root
  - api_data     : dict — output of api_extractor.extract_api_endpoints()
  - dep_data     : dict — output of dependency_extractor.extract_dependencies()

Output (RepoEvidenceManifest dict):
  {
    "has_http_api":       bool,   # Spring @RestController / FastAPI / Express routes found
    "has_grpc":           bool,   # .proto files or rpc definitions found
    "actual_endpoints":   [...],  # real extracted endpoints (method, path, handler, file)
    "has_database":       bool,   # JDBC / JPA / Hibernate / Mongoose / SQLAlchemy dep found
    "has_auth":           bool,   # Spring Security / Firebase / JWT / Passport dep found
    "has_docker":         bool,   # Dockerfile or docker-compose.yml present
    "has_kubernetes":     bool,   # k8s/ dir or manifest with 'kind: Deployment'
    "has_android":        bool,   # AndroidManifest.xml or .apk build files found
    "has_ios":            bool,   # .xcodeproj / .xcworkspace / Podfile found
    "has_desktop":        bool,   # .pbw / PowerBuilder / Electron / WinForms evidence
    "has_gdpr_mention":   bool,   # README/docs explicitly mention GDPR, PII, data protection
    "has_tests":          bool,   # test/ dir, *Test.kt, *_test.py, *.spec.ts files found
    "platform":           str,    # "android"|"ios"|"desktop"|"web"|"server"|"library"|"unknown"
    "detected_deps":      [...],  # full dependency list from dependency_extractor
    "dep_categories":     {...},  # {framework: [...], database: [...], auth: [...], ...}
    "infra_files":        [...],  # list of infra-related filenames detected
    "build_tool":         str,    # "gradle" | "maven" | "npm" | "pip" | "unknown"
    "primary_language":   str,    # from dependency_extractor language field
  }
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Any

# ---------------------------------------------------------------------------
# Dependency category keyword maps (used to group extracted deps by role)
# These map dependency NAME fragments → category bucket
# No domain rules here — we look at what's actually declared in build files
# ---------------------------------------------------------------------------

_DEP_DATABASE_KEYWORDS = [
    "jdbc", "jpa", "hibernate", "mysql", "postgres", "sqlite", "mongo",
    "sqlalchemy", "prisma", "sequelize", "typeorm", "room", "realm",
    "h2", "mariadb", "mssql", "oracle", "redis", "cassandra",
]

_DEP_AUTH_KEYWORDS = [
    "spring-security", "spring.security", "firebase", "jwt", "passport",
    "auth0", "keycloak", "okta", "shiro", "pac4j", "nimbus-jose-jwt",
    "bcrypt", "argon2", "django.contrib.auth",
]

_DEP_GRPC_KEYWORDS = [
    "grpc", "protobuf", "proto3", "io.grpc",
]

_DEP_CONTAINER_KEYWORDS = [
    "docker", "kubernetes", "k8s", "helm",
]

# ---------------------------------------------------------------------------
# GDPR / compliance mention patterns (scan README and docs only)
# ---------------------------------------------------------------------------

_GDPR_PATTERNS = re.compile(
    r"\b(gdpr|ccpa|pii|personal\s+data|data\s+protection|right\s+to\s+erasure"
    r"|data\s+subject|lawful\s+basis|privacy\s+policy|hipaa|sox|pci[-\s]dss)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Kubernetes manifest detection
# ---------------------------------------------------------------------------

_K8S_KIND_PATTERN = re.compile(
    r"^kind\s*:\s*(Deployment|StatefulSet|Service|Ingress|Pod|DaemonSet|Job|CronJob)\b",
    re.MULTILINE,
)


def _scan_gdpr_in_text(text: str) -> bool:
    """Return True if the text explicitly mentions GDPR/PII/compliance terms."""
    return bool(_GDPR_PATTERNS.search(text))


def _categorize_deps(deps: List[Dict]) -> Dict[str, List[str]]:
    """
    Group dependency names into category buckets: database, auth, grpc, infra, framework, other.
    Uses keyword matching on the dep name — reflects what's actually in build files.
    """
    categories: Dict[str, List[str]] = {
        "database":  [],
        "auth":      [],
        "grpc":      [],
        "infra":     [],
        "framework": [],
        "other":     [],
    }
    for dep in deps:
        name_lower = dep.get("name", "").lower()
        cat = dep.get("category", "")

        if any(k in name_lower for k in _DEP_DATABASE_KEYWORDS):
            categories["database"].append(dep["name"])
        elif any(k in name_lower for k in _DEP_AUTH_KEYWORDS):
            categories["auth"].append(dep["name"])
        elif any(k in name_lower for k in _DEP_GRPC_KEYWORDS):
            categories["grpc"].append(dep["name"])
        elif any(k in name_lower for k in _DEP_CONTAINER_KEYWORDS):
            categories["infra"].append(dep["name"])
        elif cat == "framework":
            categories["framework"].append(dep["name"])
        else:
            categories["other"].append(dep["name"])

    # Deduplicate each bucket
    return {k: list(dict.fromkeys(v)) for k, v in categories.items()}


def _detect_platform(
    repo_dir: Path,
    has_android: bool,
    has_ios: bool,
    has_desktop: bool,
    has_http_api: bool,
    has_grpc: bool,
) -> str:
    """
    Derive the primary platform string from evidence — without any domain keyword lists.
    Priority: android > ios > desktop > web/server > library > unknown
    """
    if has_android:
        return "android"
    if has_ios:
        return "ios"
    if has_desktop:
        return "desktop"
    if has_http_api or has_grpc:
        return "server"
    # Check for web front-end signals (index.html, package.json with react/vue/angular)
    if any(repo_dir.rglob("index.html")):
        return "web"
    return "library"


def build_evidence_manifest(
    repo_dir: str | Path,
    api_data: Dict[str, Any],
    dep_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the RepoEvidenceManifest from actual repo file system + extractor outputs.

    Parameters
    ----------
    repo_dir : path to the cloned repository root
    api_data : output of extract_api_endpoints()
    dep_data : output of extract_dependencies()

    Returns
    -------
    dict matching the RepoEvidenceManifest schema (see module docstring)
    """
    repo_dir = Path(repo_dir)
    deps: List[Dict] = dep_data.get("dependencies", [])

    # ── 1. API evidence (from api_extractor output) ───────────────────────
    actual_endpoints: List[Dict] = api_data.get("endpoints", [])
    grpc_rpcs: List[Dict] = api_data.get("grpc_rpcs", [])
    has_http_api = len(actual_endpoints) > 0
    has_grpc_from_api = len(grpc_rpcs) > 0

    # ── 2. Dependency analysis (from dependency_extractor output) ─────────
    dep_names_lower = [d.get("name", "").lower() for d in deps]

    has_database = any(
        any(k in n for k in _DEP_DATABASE_KEYWORDS) for n in dep_names_lower
    )
    has_auth_dep = any(
        any(k in n for k in _DEP_AUTH_KEYWORDS) for n in dep_names_lower
    )
    has_grpc_dep = any(
        any(k in n for k in _DEP_GRPC_KEYWORDS) for n in dep_names_lower
    )
    has_grpc = has_grpc_from_api or has_grpc_dep

    dep_categories = _categorize_deps(deps)

    # ── 3. Infrastructure file scan ───────────────────────────────────────
    infra_files: List[str] = []

    has_docker = False
    for pattern in ("Dockerfile", "dockerfile", "docker-compose.yml",
                    "docker-compose.yaml", "compose.yml", "compose.yaml"):
        matches = list(repo_dir.rglob(pattern))
        if matches:
            has_docker = True
            infra_files.extend(str(m.relative_to(repo_dir)) for m in matches)

    # Kubernetes: look for k8s/ dir OR yaml files containing 'kind: Deployment' etc.
    has_kubernetes = False
    k8s_dirs = [d for d in repo_dir.rglob("*")
                if d.is_dir() and d.name.lower() in ("k8s", "kubernetes", "helm", "charts")]
    if k8s_dirs:
        has_kubernetes = True
        infra_files.extend(str(d.relative_to(repo_dir)) for d in k8s_dirs)
    else:
        # Scan yaml files for Kubernetes kind declarations
        for yaml_file in list(repo_dir.rglob("*.yaml")) + list(repo_dir.rglob("*.yml")):
            if ".git" in str(yaml_file):
                continue
            try:
                text = yaml_file.read_text(encoding="utf-8", errors="replace")
                if _K8S_KIND_PATTERN.search(text):
                    has_kubernetes = True
                    infra_files.append(str(yaml_file.relative_to(repo_dir)))
                    break
            except Exception:
                continue

    # ── 4. Platform detection — read actual platform-specific files ───────
    # Android
    android_files = list(repo_dir.rglob("AndroidManifest.xml"))
    has_android = len(android_files) > 0

    # iOS
    ios_signals = (
        list(repo_dir.rglob("*.xcodeproj")) +
        list(repo_dir.rglob("*.xcworkspace")) +
        list(repo_dir.rglob("Podfile"))
    )
    has_ios = len(ios_signals) > 0

    # Desktop (PowerBuilder, Electron, WinForms, WPF)
    desktop_signals = (
        list(repo_dir.rglob("*.pbl")) +      # PowerBuilder library
        list(repo_dir.rglob("*.pbt")) +      # PowerBuilder target
        list(repo_dir.rglob("*.pbw")) +      # PowerBuilder workspace
        list(repo_dir.rglob("*.sln")) +      # Visual Studio solution (WinForms/WPF)
        list(repo_dir.rglob("*.csproj"))     # C# project (may be desktop)
    )
    # Electron: package.json with "electron" dep (checked via dep_names_lower)
    has_electron = "electron" in " ".join(dep_names_lower)
    has_desktop = len(desktop_signals) > 0 or has_electron

    # ── 5. Auth evidence (deps + auth-related source directories) ─────────
    auth_dirs = [d for d in repo_dir.rglob("*")
                 if d.is_dir() and d.name.lower() in ("auth", "security", "authentication",
                                                        "authorization", "identity")]
    has_auth = has_auth_dep or len(auth_dirs) > 0

    # ── 6. Test coverage evidence ─────────────────────────────────────────
    test_dirs = [d for d in repo_dir.rglob("*")
                 if d.is_dir() and d.name.lower() in ("test", "tests", "__tests__", "spec")]
    test_files = (
        list(repo_dir.rglob("*Test.kt")) +
        list(repo_dir.rglob("*Test.java")) +
        list(repo_dir.rglob("*_test.py")) +
        list(repo_dir.rglob("*.spec.ts")) +
        list(repo_dir.rglob("*.test.ts")) +
        list(repo_dir.rglob("*.test.js"))
    )
    has_tests = len(test_dirs) > 0 or len(test_files) > 0

    # ── 7. GDPR / compliance mention scan (README + docs only) ───────────
    has_gdpr_mention = False
    gdpr_scan_targets = (
        list(repo_dir.glob("README*")) +
        list(repo_dir.glob("readme*")) +
        list(repo_dir.rglob("PRIVACY*")) +
        list(repo_dir.rglob("privacy*")) +
        list(repo_dir.rglob("*.md"))[:20]   # cap to avoid scanning huge repos
    )
    for doc_file in gdpr_scan_targets:
        try:
            text = doc_file.read_text(encoding="utf-8", errors="replace")
            if _scan_gdpr_in_text(text):
                has_gdpr_mention = True
                break
        except Exception:
            continue

    # ── 8. Platform string ────────────────────────────────────────────────
    platform = _detect_platform(
        repo_dir, has_android, has_ios, has_desktop, has_http_api, has_grpc
    )

    # ── Assemble manifest ─────────────────────────────────────────────────
    manifest = {
        "has_http_api":     has_http_api,
        "has_grpc":         has_grpc,
        "actual_endpoints": actual_endpoints,
        "grpc_rpcs":        grpc_rpcs,
        "has_database":     has_database,
        "has_auth":         has_auth,
        "has_docker":       has_docker,
        "has_kubernetes":   has_kubernetes,
        "has_android":      has_android,
        "has_ios":          has_ios,
        "has_desktop":      has_desktop,
        "has_gdpr_mention": has_gdpr_mention,
        "has_tests":        has_tests,
        "platform":         platform,
        "detected_deps":    deps,
        "dep_categories":   dep_categories,
        "infra_files":      list(dict.fromkeys(infra_files)),  # deduplicate
        "build_tool":       dep_data.get("build_tool", "unknown"),
        "primary_language": dep_data.get("language", "unknown"),
    }

    _log_manifest_summary(manifest)
    return manifest


def _log_manifest_summary(m: Dict) -> None:
    """Print a one-line summary of the manifest for pipeline logs."""
    flags = []
    if m["has_http_api"]:   flags.append(f"HTTP({len(m['actual_endpoints'])} endpoints)")
    if m["has_grpc"]:       flags.append("gRPC")
    if m["has_database"]:   flags.append("DB")
    if m["has_auth"]:       flags.append("Auth")
    if m["has_docker"]:     flags.append("Docker")
    if m["has_kubernetes"]: flags.append("K8s")
    if m["has_android"]:    flags.append("Android")
    if m["has_ios"]:        flags.append("iOS")
    if m["has_desktop"]:    flags.append("Desktop")
    if m["has_gdpr_mention"]: flags.append("GDPR-mention")
    if m["has_tests"]:      flags.append("Tests")

    print(
        f"[EVIDENCE MANIFEST] platform={m['platform']} | "
        f"lang={m['primary_language']} | build={m['build_tool']} | "
        f"signals=[{', '.join(flags) or 'none'}]"
    )
