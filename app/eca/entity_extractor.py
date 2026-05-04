"""
entity_extractor.py — Phase 3 Extractor
------------------------------------------
Extracts domain entity / data model classes from source code.

Scans: All .kt, .java files for @Entity, data class, @Table annotations.

Output:
  {
    "entities": [
      {
        "name": str,
        "source_file": str,
        "table_name": str | null,
        "fields": [str],
        "entity_type": "jpa_entity" | "data_class" | "proto_message"
      }
    ]
  }
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Any


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Kotlin data class: data class User(val id: Long, val name: String)
_KOTLIN_DATA_CLASS = re.compile(
    r'data\s+class\s+(\w+)\s*\(([^)]*)\)',
    re.DOTALL,
)

# JPA @Entity annotation followed by class declaration
_JPA_ENTITY = re.compile(
    r'@Entity\b.*?(?:class|object)\s+(\w+)',
    re.DOTALL,
)

# @Table(name = "users")
_TABLE_NAME = re.compile(
    r'''@Table\s*\(\s*name\s*=\s*["'](\w+)["']''',
    re.IGNORECASE,
)

# Proto message definition: message User { ... }
_PROTO_MESSAGE = re.compile(
    r'message\s+(\w+)\s*\{([^}]*)\}',
    re.DOTALL,
)

# Kotlin/Java field: val name: String  or  private String name;
_KOTLIN_FIELD = re.compile(r'(?:val|var)\s+(\w+)\s*:')
_JAVA_FIELD = re.compile(r'(?:private|protected|public)\s+\w+\s+(\w+)\s*[;=]')

# Proto field: string name = 1;
_PROTO_FIELD = re.compile(r'(?:string|int32|int64|bool|float|double|bytes|\w+)\s+(\w+)\s*=\s*\d+')


def _extract_kotlin_fields(params_block: str) -> List[str]:
    """Extract parameter names from a Kotlin data class constructor."""
    return _KOTLIN_FIELD.findall(params_block)


def _relative_path(file_path: Path, repo_dir: Path) -> str:
    """Return a relative path string for display."""
    try:
        return str(file_path.relative_to(repo_dir)).replace("\\", "/")
    except ValueError:
        return str(file_path).replace("\\", "/")


def extract_entities(repo_dir: Path | str) -> Dict[str, Any]:
    """
    Scan a repository directory for domain entity definitions.

    Returns a dict with key "entities" containing a list of detected entities.
    """
    repo_dir = Path(repo_dir)
    entities: List[Dict[str, Any]] = []
    seen_names: set = set()

    # --- Kotlin / Java files ---
    source_files = list(repo_dir.rglob("*.kt")) + list(repo_dir.rglob("*.java"))
    for sf in source_files:
        # Skip test files
        rel = _relative_path(sf, repo_dir)
        if "/test/" in rel.lower() or "test" in sf.stem.lower() and sf.stem.lower() != sf.stem.lower().replace("test", ""):
            continue

        try:
            text = sf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Detect @Table name (applies to any entity in the file)
        table_match = _TABLE_NAME.search(text)
        table_name = table_match.group(1) if table_match else None

        # JPA @Entity classes
        for m in _JPA_ENTITY.finditer(text):
            name = m.group(1)
            if name in seen_names:
                continue
            seen_names.add(name)

            # Try to extract fields from the class body
            fields = _KOTLIN_FIELD.findall(text) or _JAVA_FIELD.findall(text)
            # Filter out common noise
            fields = [f for f in fields if f not in ("serialVersionUID", "Companion")]

            entities.append({
                "name": name,
                "source_file": rel,
                "table_name": table_name,
                "fields": fields[:15],  # Cap field count
                "entity_type": "jpa_entity",
            })

        # Kotlin data classes (not already captured as @Entity)
        for m in _KOTLIN_DATA_CLASS.finditer(text):
            name = m.group(1)
            if name in seen_names:
                continue

            # Skip DTOs and request/response objects — only capture domain models
            params_block = m.group(2)
            fields = _extract_kotlin_fields(params_block)

            if len(fields) < 2:
                continue  # Too trivial

            seen_names.add(name)
            entities.append({
                "name": name,
                "source_file": rel,
                "table_name": table_name,
                "fields": fields[:15],
                "entity_type": "data_class",
            })

    # --- Proto files ---
    proto_files = list(repo_dir.rglob("*.proto"))
    for pf in proto_files:
        try:
            text = pf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        rel = _relative_path(pf, repo_dir)
        for m in _PROTO_MESSAGE.finditer(text):
            name = m.group(1)
            if name in seen_names:
                continue
            seen_names.add(name)

            body = m.group(2)
            fields = _PROTO_FIELD.findall(body)

            entities.append({
                "name": name,
                "source_file": rel,
                "table_name": None,
                "fields": fields[:15],
                "entity_type": "proto_message",
            })

    return {"entities": entities}
