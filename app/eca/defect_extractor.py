"""
defect_extractor.py — Phase 3 Extractor
------------------------------------------
Extracts known defects, code smells, and risk signals from source code.

Scans: All source files for TODO/FIXME, @Deprecated, jcenter(), hardcoded creds,
       Thread.sleep() in non-test code, deprecated Kubernetes API versions, etc.

Output:
  {
    "defects": [
      {
        "id": "BUG-NN",
        "type": str,
        "severity": "critical" | "high" | "medium" | "low",
        "file": str,
        "line": int,
        "description": str
      }
    ]
  }
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Any


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

_PATTERNS = [
    # (regex, type, severity, description_template)
    (
        re.compile(r'(//\s*TODO\b[:\s]*(.*))', re.IGNORECASE),
        "todo",
        "low",
        "TODO comment: {detail}",
    ),
    (
        re.compile(r'(//\s*FIXME\b[:\s]*(.*))', re.IGNORECASE),
        "fixme",
        "medium",
        "FIXME comment: {detail}",
    ),
    (
        re.compile(r'(//\s*HACK\b[:\s]*(.*))', re.IGNORECASE),
        "hack",
        "medium",
        "HACK comment: {detail}",
    ),
    (
        re.compile(r'(@Deprecated\b)', re.IGNORECASE),
        "deprecated_api",
        "medium",
        "Deprecated API usage detected.",
    ),
    (
        re.compile(r'(jcenter\s*\(\s*\))', re.IGNORECASE),
        "dead_repository",
        "critical",
        "jcenter() repository reference — permanently shut down since Feb 2022.",
    ),
    (
        re.compile(r'(Thread\.sleep\s*\()', re.IGNORECASE),
        "blocking_call",
        "medium",
        "Thread.sleep() in production code — can cause thread starvation.",
    ),
    (
        re.compile(r'''(password\s*=\s*["'][^"']+["'])''', re.IGNORECASE),
        "hardcoded_credential",
        "critical",
        "Hardcoded password detected in source code.",
    ),
    (
        re.compile(r'''(api[_-]?key\s*=\s*["'][^"']+["'])''', re.IGNORECASE),
        "hardcoded_credential",
        "critical",
        "Hardcoded API key detected in source code.",
    ),
    (
        re.compile(r'(extensions/v1beta1)', re.IGNORECASE),
        "deprecated_k8s_api",
        "high",
        "Deprecated Kubernetes API version 'extensions/v1beta1' — removed in k8s 1.22+.",
    ),
    (
        re.compile(r'(apps/v1beta1|apps/v1beta2)', re.IGNORECASE),
        "deprecated_k8s_api",
        "high",
        "Deprecated Kubernetes API version — use 'apps/v1' instead.",
    ),
]

# Files/directories to skip
_SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "build", "target", ".gradle"}
_BINARY_EXTS = {".jar", ".class", ".png", ".jpg", ".gif", ".ico", ".woff", ".ttf", ".zip", ".tar", ".gz"}


def _relative_path(file_path: Path, repo_dir: Path) -> str:
    try:
        return str(file_path.relative_to(repo_dir)).replace("\\", "/")
    except ValueError:
        return str(file_path).replace("\\", "/")


def _should_skip(path: Path) -> bool:
    """Check if this file/dir should be skipped."""
    for part in path.parts:
        if part in _SKIP_DIRS:
            return True
    if path.suffix.lower() in _BINARY_EXTS:
        return True
    return False


def extract_defects(repo_dir: Path | str) -> Dict[str, Any]:
    """
    Scan a repository directory for known defects and code smells.

    Returns a dict with key "defects" containing a list of detected issues.
    """
    repo_dir = Path(repo_dir)
    defects: List[Dict[str, Any]] = []
    bug_counter = 0

    # Scan all text files
    scannable_exts = {
        ".kt", ".java", ".py", ".js", ".ts", ".go", ".rs",
        ".xml", ".yaml", ".yml", ".json", ".gradle", ".kts",
        ".properties", ".toml", ".cfg", ".ini",
        ".proto", ".sql",
        ".dockerfile", ".sh", ".bat",
    }

    for fp in repo_dir.rglob("*"):
        if not fp.is_file():
            continue
        if _should_skip(fp):
            continue

        # Check extension or special filenames
        if fp.suffix.lower() not in scannable_exts and fp.name.lower() not in ("dockerfile", "makefile", "jenkinsfile"):
            continue

        rel = _relative_path(fp, repo_dir)
        is_test_file = "/test/" in rel.lower() or "test" in fp.stem.lower()

        try:
            lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue

        for line_num, line in enumerate(lines, start=1):
            for pattern, defect_type, severity, desc_template in _PATTERNS:
                m = pattern.search(line)
                if not m:
                    continue

                # Skip Thread.sleep in test files
                if defect_type == "blocking_call" and is_test_file:
                    continue

                # Build description
                detail = m.group(2).strip() if m.lastindex and m.lastindex >= 2 else ""
                description = desc_template.format(detail=detail) if "{detail}" in desc_template else desc_template

                bug_counter += 1
                defects.append({
                    "id": f"BUG-{bug_counter:02d}",
                    "type": defect_type,
                    "severity": severity,
                    "file": rel,
                    "line": line_num,
                    "description": description,
                })

    # Sort by severity: critical > high > medium > low
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    defects.sort(key=lambda d: (severity_order.get(d["severity"], 9), d["file"], d["line"]))

    # Re-number after sort
    for i, d in enumerate(defects, start=1):
        d["id"] = f"BUG-{i:02d}"

    return {"defects": defects}
