"""
api_extractor.py — Phase 3 Extractor
---------------------------------------
Extracts REST API endpoints and gRPC RPC definitions from source code.

Scans: .kt/.java files for Spring MVC annotations, .proto files for rpc declarations.

Output:
  {
    "endpoints": [
      { "method": str, "path": str, "handler": str, "source_file": str }
    ],
    "grpc_rpcs": [
      { "service": str, "rpc": str, "request": str, "response": str, "source_file": str }
    ]
  }
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Any


# ---------------------------------------------------------------------------
# Spring MVC patterns
# ---------------------------------------------------------------------------

# @RestController or @Controller class name
_CONTROLLER_CLASS = re.compile(
    r'@(?:Rest)?Controller\b.*?class\s+(\w+)',
    re.DOTALL,
)

# @RequestMapping("/api/v1/users") at class level
_CLASS_MAPPING = re.compile(
    r'''@RequestMapping\s*\(\s*(?:value\s*=\s*)?["']([^"']+)["']''',
)

# @GetMapping("/list"), @PostMapping, @PutMapping, @DeleteMapping, @PatchMapping
_METHOD_MAPPING = re.compile(
    r'''@(Get|Post|Put|Delete|Patch)Mapping\s*\(\s*(?:value\s*=\s*)?["']([^"']*?)["']''',
    re.IGNORECASE,
)

# @RequestMapping(method = RequestMethod.GET, value = "/list")
_REQUEST_MAPPING_METHOD = re.compile(
    r'''@RequestMapping\s*\([^)]*method\s*=\s*\[?\s*RequestMethod\.(\w+)[^)]*value\s*=\s*["']([^"']+)["']''',
    re.DOTALL | re.IGNORECASE,
)

# fun methodName( or public ReturnType methodName(
_FUNCTION_NAME = re.compile(r'(?:fun|public\s+\w+)\s+(\w+)\s*\(')

# ---------------------------------------------------------------------------
# gRPC / Proto patterns
# ---------------------------------------------------------------------------

# service ItemaeService { ... }
_PROTO_SERVICE = re.compile(
    r'service\s+(\w+)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}',
    re.DOTALL,
)

# rpc CreateUser (CreateUserRequest) returns (CreateUserResponse)
_PROTO_RPC = re.compile(
    r'rpc\s+(\w+)\s*\(\s*(\w+)\s*\)\s*returns\s*\(\s*(\w+)\s*\)',
)


def _relative_path(file_path: Path, repo_dir: Path) -> str:
    try:
        return str(file_path.relative_to(repo_dir)).replace("\\", "/")
    except ValueError:
        return str(file_path).replace("\\", "/")


def extract_api_endpoints(repo_dir: Path | str) -> Dict[str, Any]:
    """
    Scan a repository directory for REST endpoints and gRPC RPC definitions.
    """
    repo_dir = Path(repo_dir)
    endpoints: List[Dict[str, str]] = []
    grpc_rpcs: List[Dict[str, str]] = []

    # --- Spring MVC REST endpoints ---
    source_files = list(repo_dir.rglob("*.kt")) + list(repo_dir.rglob("*.java"))
    for sf in source_files:
        rel = _relative_path(sf, repo_dir)
        # Skip test files
        if "/test/" in rel.lower():
            continue

        try:
            text = sf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Check if this is a controller file
        ctrl_match = _CONTROLLER_CLASS.search(text)
        if not ctrl_match:
            continue

        controller_name = ctrl_match.group(1)

        # Find class-level base path
        base_path = ""
        class_mapping = _CLASS_MAPPING.search(text)
        if class_mapping:
            base_path = class_mapping.group(1).rstrip("/")

        # Find method-level mappings
        # Split text into function-level chunks for handler name resolution
        lines = text.split("\n")
        for i, line in enumerate(lines):
            m = _METHOD_MAPPING.search(line)
            if m:
                http_method = m.group(1).upper()
                path = m.group(2)
                full_path = f"{base_path}/{path}".replace("//", "/") if path else base_path or "/"

                # Look for function name on the next few lines
                handler = controller_name
                for j in range(i, min(i + 5, len(lines))):
                    fn_match = _FUNCTION_NAME.search(lines[j])
                    if fn_match:
                        handler = f"{controller_name}.{fn_match.group(1)}"
                        break

                endpoints.append({
                    "method": http_method,
                    "path": full_path,
                    "handler": handler,
                    "source_file": rel,
                })

            # Also check @RequestMapping with explicit method
            rm = _REQUEST_MAPPING_METHOD.search(line)
            if rm:
                http_method = rm.group(1).upper()
                path = rm.group(2)
                full_path = f"{base_path}/{path}".replace("//", "/")

                handler = controller_name
                for j in range(i, min(i + 5, len(lines))):
                    fn_match = _FUNCTION_NAME.search(lines[j])
                    if fn_match:
                        handler = f"{controller_name}.{fn_match.group(1)}"
                        break

                endpoints.append({
                    "method": http_method,
                    "path": full_path,
                    "handler": handler,
                    "source_file": rel,
                })

    # --- gRPC / Proto RPCs ---
    proto_files = list(repo_dir.rglob("*.proto"))
    for pf in proto_files:
        rel = _relative_path(pf, repo_dir)
        try:
            text = pf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for svc_match in _PROTO_SERVICE.finditer(text):
            service_name = svc_match.group(1)
            service_body = svc_match.group(2)

            for rpc_match in _PROTO_RPC.finditer(service_body):
                grpc_rpcs.append({
                    "service": service_name,
                    "rpc": rpc_match.group(1),
                    "request": rpc_match.group(2),
                    "response": rpc_match.group(3),
                    "source_file": rel,
                })

    return {
        "endpoints": endpoints,
        "grpc_rpcs": grpc_rpcs,
    }
