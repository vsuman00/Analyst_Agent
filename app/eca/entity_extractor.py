"""
entity_extractor.py — Phase 3 Extractor / Phase 1.5 Sub-Extractor
------------------------------------------------------------------
Extracts domain entity / data model classes from source code.

Supports hybrid analysis:
- When OPENAI_API_KEY is present: Employs LLM-assisted semantic parsing 
  across all major programming languages (Python, Go, JS/TS, Rust, Java, etc.)
  with candidate file pre-filtering for fast and cost-effective scanning.
- Fallback / Offline: Performs local, high-precision deterministic regex 
  parsing of Java/Kotlin JPA entities, Kotlin data classes, and Protobuf schemas.

Output:
  {
    "entities": [
      {
        "name": str,
        "source_file": str,
        "table_name": str | null,
        "fields": [str],
        "entity_type": "jpa_entity" | "data_class" | "proto_message" | "generic_model"
      }
    ]
  }
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Any

# ---------------------------------------------------------------------------
# Regex Patterns (Deterministic Local Fallback)
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


# ---------------------------------------------------------------------------
# Public Entry Point
# ---------------------------------------------------------------------------

def extract_entities(repo_dir: Path | str) -> Dict[str, Any]:
    """
    Scan a repository directory for domain entity definitions.
    Uses hybrid logic: LLM-assisted semantic parsing if API key is present,
    falling back to deterministic regex parsing.
    """
    repo_dir = Path(repo_dir)
    api_key = os.environ.get("OPENAI_API_KEY", "")

    if api_key:
        try:
            print("[ENTITY EXTRACTOR] API Key detected. Performing LLM semantic extraction...")
            return _extract_entities_llm(repo_dir)
        except Exception as e:
            print(f"[ENTITY EXTRACTOR] LLM extraction failed: {e}. Falling back to deterministic regex...")
            # Fall through to deterministic parsing

    # Local fallback
    return _extract_entities_regex(repo_dir)


# ---------------------------------------------------------------------------
# 1. Deterministic Regex Parsing (Local Fallback)
# ---------------------------------------------------------------------------

def _extract_entities_regex(repo_dir: Path) -> Dict[str, Any]:
    """Extract entities locally using fast regex parsing (original codebase implementation)."""
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


# ---------------------------------------------------------------------------
# 2. Semantic LLM Parsing (Cross-Language Parser)
# ---------------------------------------------------------------------------

def _extract_entities_llm(repo_dir: Path) -> Dict[str, Any]:
    """Uses OpenAI LLM to semantically analyze codebase files and extract domain entities."""
    from app.utils.llm_client import llm_json_call
    from app.schemas.models import EntityExtractionResult

    candidate_files = []
    
    # Common backend/model extensions
    target_extensions = {
        ".py", ".java", ".kt", ".proto", ".go", ".rs", ".ts", ".js", ".cs", ".rb", ".php"
    }
    
    # Walk the repository
    for p in repo_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in target_extensions:
            # Skip test files, build outputs, node_modules, virtual envs
            rel = _relative_path(p, repo_dir)
            rel_lower = rel.lower()
            if (
                "test" in rel_lower or 
                "node_modules" in rel_lower or 
                "venv" in rel_lower or 
                ".git" in rel_lower or
                "dist" in rel_lower or
                "build" in rel_lower
            ):
                continue
            
            # Read first 3KB to check if it represents a model or entity definition
            try:
                content = p.read_text(encoding="utf-8", errors="replace")[:3000]
                content_lower = content.lower()
                # Heuristic: looks for class, struct, schema, table definitions or common ORM/entity decorations
                is_candidate = (
                    "class " in content or
                    "struct " in content or
                    "interface " in content or
                    "message " in p.name or  # proto message
                    "db.model" in content_lower or
                    "schema" in content_lower or
                    "entity" in content_lower or
                    "@table" in content_lower or
                    "jpa" in content_lower or
                    "mongoose" in content_lower or
                    "prisma" in content_lower or
                    "gorm" in content_lower or
                    "diesel" in content_lower
                )
                if is_candidate:
                    candidate_files.append((rel, content))
            except Exception:
                continue

    if not candidate_files:
        return {"entities": []}

    # Cap candidate files to prevent exceeding context window (e.g. top 15 most promising)
    # Priority logic: sort files so that those containing "model", "entity", "schema" or "dto" in their path come first
    def file_priority(item):
        path_lower = item[0].lower()
        if "model" in path_lower or "entity" in path_lower:
            return 0
        if "schema" in path_lower or "dto" in path_lower:
            return 1
        return 2

    candidate_files.sort(key=file_priority)
    candidate_files = candidate_files[:15]

    # Call LLM to parse all candidate models in one single pass using JSON mode
    system_prompt = (
        "You are an expert static analysis agent. Analyze the provided source code snippets "
        "and extract any domain entities, database tables, or data structures that act as "
        "primary data models/representations.\n\n"
        "STRICT RULES:\n"
        "- Do NOT invent fields or entities. Only extract what is present in the provided snippets.\n"
        "- The fields list should be the variable/member names inside the class/struct/message definition.\n"
        "- For entity_type, use: 'jpa_entity' (for Java/Kotlin JPA annotated classes), "
        "'data_class' (for Kotlin data classes), 'proto_message' (for Protobuf messages), "
        "or 'generic_model' (for Python models, TypeScript interfaces, Go structs, etc.).\n\n"
        "Respond ONLY with a JSON object in this format:\n"
        "{\n"
        '  "entities": [\n'
        "    {\n"
        '      "name": "User",\n'
        '      "source_file": "relative/path/to/file.py",\n'
        '      "table_name": "users" or null,\n'
        '      "fields": ["id", "username", "email"],\n'
        '      "entity_type": "jpa_entity" | "data_class" | "proto_message" | "generic_model"\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    code_ctx = "\n\n".join([
        f"=== File: {rel} ===\n{content}" for rel, content in candidate_files
    ])

    user_prompt = f"Analyze the following code files and extract the domain entities:\n\n{code_ctx}"

    # Use max_tokens=1500 to allow sufficient room for JSON structure
    result = llm_json_call(system_prompt, user_prompt, max_tokens=1500)

    # Validate output schema strictly using Pydantic
    validated = EntityExtractionResult(**result)
    return validated.model_dump()
