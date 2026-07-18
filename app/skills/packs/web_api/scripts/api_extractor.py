"""
api_extractor.py — Web API Skill Pack Extraction Script
---------------------------------------------------------
Extracts HTTP endpoints, authentication patterns, and middleware signals
from web API repositories.

Usage:
    python scripts/api_extractor.py <repo_dir> <output_file> <subcommand>

Subcommands:
    contracts   — Extract HTTP endpoints (method + path + handler)
    auth        — Detect authentication mechanisms
    middleware  — Detect middleware chains and error handling patterns

Output is always JSON written to <output_file>.
Uses ONLY stdlib — no pip installs required.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Any


# ---------------------------------------------------------------------------
# HTTP Method Detection Patterns (framework-agnostic)
# ---------------------------------------------------------------------------

# Decorator-based patterns: @app.get("/path"), @router.post("/path"), etc.
_DECORATOR_RE = re.compile(
    r"""@\w+\.(get|post|put|delete|patch|head|options)\s*\(\s*["']([^"']+)["']""",
    re.IGNORECASE,
)

# Express-style: app.get("/path", handler) or router.get("/path", handler)
_EXPRESS_RE = re.compile(
    r"""\b(?:app|router|server)\s*\.\s*(get|post|put|delete|patch)\s*\(\s*["'`]([^"'`]+)["'`]""",
    re.IGNORECASE,
)

# Spring MVC: @GetMapping("/path"), @PostMapping("/path"), @RequestMapping(...)
_SPRING_RE = re.compile(
    r"""@(Get|Post|Put|Delete|Patch|Request)Mapping\s*\(\s*(?:value\s*=\s*)?["']([^"']+)["']""",
    re.IGNORECASE,
)

# Go Gin/Fiber: r.GET("/path", handler)
_GO_RE = re.compile(
    r"""\b\w+\.(GET|POST|PUT|DELETE|PATCH)\s*\(\s*["']([^"']+)["']""",
)

# Proto gRPC: rpc MethodName (Request) returns (Response)
_GRPC_RE = re.compile(
    r"""rpc\s+(\w+)\s*\(""",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Auth Detection Patterns
# ---------------------------------------------------------------------------

_AUTH_PATTERNS = {
    "jwt": [
        re.compile(r"jwt\.decode|jwt\.verify|JwtModule|@UseGuards.*JwtAuth|Bearer\s+token", re.IGNORECASE),
        re.compile(r"jsonwebtoken|pyjwt|jose|JWTAuth|jwt_required", re.IGNORECASE),
    ],
    "oauth2": [
        re.compile(r"OAuth2|oauth2|authorization_code|client_credentials|OAuth2Scheme", re.IGNORECASE),
        re.compile(r"passport\.authenticate|OAuth2Client", re.IGNORECASE),
    ],
    "session": [
        re.compile(r"session\.get|req\.session|@login_required|SessionAuthentication", re.IGNORECASE),
        re.compile(r"express-session|SessionMiddleware", re.IGNORECASE),
    ],
    "api_key": [
        re.compile(r"api[_-]?key|x-api-key|ApiKeyAuth|APIKeyHeader", re.IGNORECASE),
    ],
    "basic": [
        re.compile(r"BasicAuth|HTTPBasic|basic_auth|Authorization:\s*Basic", re.IGNORECASE),
    ],
}


# ---------------------------------------------------------------------------
# Middleware Patterns
# ---------------------------------------------------------------------------

_MIDDLEWARE_PATTERNS = {
    "cors": re.compile(r"CORSMiddleware|cors\(\)|enable_cors|Access-Control-Allow", re.IGNORECASE),
    "rate_limiting": re.compile(r"rate[_-]?limit|throttle|RateLimiter|express-rate-limit", re.IGNORECASE),
    "logging": re.compile(r"LoggingMiddleware|morgan|winston|structlog|request_logger", re.IGNORECASE),
    "error_handler": re.compile(r"@exception_handler|error[_-]?handler|@ControllerAdvice|app\.use.*err", re.IGNORECASE),
    "validation": re.compile(r"@Body|@Valid|class-validator|marshmallow|pydantic", re.IGNORECASE),
    "compression": re.compile(r"GZipMiddleware|compression\(\)|shrink-ray", re.IGNORECASE),
}


# ---------------------------------------------------------------------------
# File Walker (only source files, skip vendored/binary)
# ---------------------------------------------------------------------------

_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", "venv", ".venv", "vendor",
    "dist", "build", ".next", "target", ".gradle", ".idea",
}

_SOURCE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".kt",
    ".go", ".rs", ".rb", ".proto", ".cs", ".ex", ".exs",
}


def _walk_source_files(repo_dir: str) -> List[tuple[str, str]]:
    """Walk repo and yield (relative_path, content) for source files."""
    results = []
    root = Path(repo_dir)
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped directories
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

        rel_dir = Path(dirpath).relative_to(root)
        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext not in _SOURCE_EXTS:
                continue

            fpath = Path(dirpath) / fname
            if fpath.stat().st_size > 500_000:  # skip >500KB files
                continue

            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                rel = str(rel_dir / fname)
                results.append((rel, content))
            except (OSError, UnicodeDecodeError):
                continue
    return results


# ---------------------------------------------------------------------------
# Subcommand: contracts
# ---------------------------------------------------------------------------

def cmd_contracts(repo_dir: str) -> Dict[str, Any]:
    """Extract HTTP endpoints and gRPC RPCs."""
    endpoints = []
    grpc_methods = []

    for rel_path, content in _walk_source_files(repo_dir):
        # HTTP endpoints
        for pattern in [_DECORATOR_RE, _EXPRESS_RE, _SPRING_RE, _GO_RE]:
            for match in pattern.finditer(content):
                method = match.group(1).upper()
                path = match.group(2)
                # Skip boilerplate
                if path.rstrip("/") in ("/health", "/healthz", "/metrics", "/docs", "/redoc", "/openapi.json"):
                    continue
                endpoints.append({
                    "method": method,
                    "path": path,
                    "source_file": rel_path,
                })

        # gRPC RPCs
        for match in _GRPC_RE.finditer(content):
            grpc_methods.append({
                "method": "gRPC",
                "path": match.group(1),
                "source_file": rel_path,
            })

    # Dedup by (method, path)
    seen = set()
    deduped = []
    for ep in endpoints + grpc_methods:
        key = (ep["method"], ep["path"])
        if key not in seen:
            seen.add(key)
            deduped.append(ep)

    # Generate features from endpoints
    features = []
    if deduped:
        # Group by path prefix for feature generation
        path_groups: Dict[str, List[str]] = {}
        for ep in deduped:
            parts = ep["path"].strip("/").split("/")
            prefix = parts[0] if parts else "root"
            path_groups.setdefault(prefix, []).append(ep["path"])

        for prefix, paths in path_groups.items():
            features.append({
                "name": f"{prefix}_api_surface",
                "description": f"API endpoints under /{prefix} ({len(paths)} routes: {', '.join(paths[:5])})",
                "confidence": 0.85,
                "source_modules": [prefix],
            })

    return {
        "endpoints": deduped,
        "total_endpoints": len(deduped),
        "features": features,
    }


# ---------------------------------------------------------------------------
# Subcommand: auth
# ---------------------------------------------------------------------------

def cmd_auth(repo_dir: str) -> Dict[str, Any]:
    """Detect authentication mechanisms."""
    auth_signals: Dict[str, List[str]] = {}  # auth_type → list of evidence strings
    files_with_auth: List[str] = []

    for rel_path, content in _walk_source_files(repo_dir):
        for auth_type, patterns in _AUTH_PATTERNS.items():
            for pattern in patterns:
                matches = pattern.findall(content)
                if matches:
                    auth_signals.setdefault(auth_type, []).extend(matches[:3])
                    if rel_path not in files_with_auth:
                        files_with_auth.append(rel_path)

    # Determine dominant auth type
    if not auth_signals:
        return {
            "auth_type": "none_detected",
            "auth_signals": [],
            "features": [],
        }

    dominant = max(auth_signals, key=lambda k: len(auth_signals[k]))
    all_signals = []
    for sigs in auth_signals.values():
        all_signals.extend(sigs)

    features = [{
        "name": f"{dominant}_authentication",
        "description": f"Authentication using {dominant.upper()} mechanism. Evidence in: {', '.join(files_with_auth[:5])}",
        "confidence": 0.9,
        "source_modules": files_with_auth[:5],
    }]

    # Add secondary auth types as lower-confidence features
    for auth_type, sigs in auth_signals.items():
        if auth_type != dominant and len(sigs) >= 2:
            features.append({
                "name": f"{auth_type}_authentication",
                "description": f"Secondary auth mechanism: {auth_type.upper()}",
                "confidence": 0.6,
                "source_modules": [],
            })

    return {
        "auth_type": dominant,
        "all_auth_types": list(auth_signals.keys()),
        "auth_signals": list(set(all_signals))[:20],
        "features": features,
    }


# ---------------------------------------------------------------------------
# Subcommand: middleware
# ---------------------------------------------------------------------------

def cmd_middleware(repo_dir: str) -> Dict[str, Any]:
    """Detect middleware and error handling patterns."""
    detected: Dict[str, List[str]] = {}

    for rel_path, content in _walk_source_files(repo_dir):
        for mw_name, pattern in _MIDDLEWARE_PATTERNS.items():
            if pattern.search(content):
                detected.setdefault(mw_name, []).append(rel_path)

    features = []
    for mw_name, files in detected.items():
        features.append({
            "name": f"{mw_name}_middleware",
            "description": f"{mw_name.replace('_', ' ').title()} middleware detected in {len(files)} file(s)",
            "confidence": 0.75,
            "source_modules": files[:3],
        })

    return {
        "middleware_detected": list(detected.keys()),
        "middleware_files": {k: v[:3] for k, v in detected.items()},
        "features": features,
    }


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Web API Skill Pack — Extract HTTP endpoints, auth patterns, and middleware"
    )
    parser.add_argument("repo_dir", help="Path to cloned repository root")
    parser.add_argument("output_file", help="Path to write JSON output")
    parser.add_argument(
        "subcommand",
        choices=["contracts", "auth", "middleware", "extract"],
        help="Extraction subcommand",
    )
    args = parser.parse_args()

    if not Path(args.repo_dir).is_dir():
        print(f"Error: {args.repo_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Map subcommands
    handlers = {
        "contracts": cmd_contracts,
        "auth": cmd_auth,
        "middleware": cmd_middleware,
        "extract": lambda d: {
            **cmd_contracts(d),
            **cmd_auth(d),
            "middleware": cmd_middleware(d),
        },
    }

    handler = handlers[args.subcommand]
    result = handler(args.repo_dir)

    # Write output
    out = Path(args.output_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"Success! {args.subcommand} → {out} ({len(result.get('features', []))} features)")


if __name__ == "__main__":
    main()
