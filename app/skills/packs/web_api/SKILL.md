---
name: web-api-analysis
version: "1.0"
description: >-
  Deep analysis pack for REST, GraphQL, and gRPC web service repositories.
  Activate when HTTP routes are detected, has_http_api or has_grpc evidence
  flags are true, or web framework dependencies (FastAPI, Flask, Express,
  Spring, Django, Rails, Gin, Actix, Fiber) are found in build files.
  DO NOT activate for pure CLI tools, desktop apps, or ML-only notebooks.

detection_signals:
  evidence_flags: [has_http_api, has_grpc]
  dependency_keywords: [fastapi, flask, django, express, koa, hapi, nestjs, spring, spring-boot, gin, actix-web, fiber, rails, sinatra, phoenix]
  file_patterns: ["**/routes/**", "**/controllers/**", "**/*.proto", "**/swagger*", "**/openapi*", "**/api/**"]
  confidence_threshold: 0.5

nfr_emphasis: [api_latency_p99, throughput_rps, api_versioning, rate_limiting, backward_compatibility]
memory_tags: [api_design, rest_patterns, grpc, auth_flows, http_endpoints]
brd_section_notes:
  section_5: "Focus on endpoint contracts, request/response schemas, error codes, and API versioning strategy"
  section_6: "Emphasise latency SLAs, throughput targets, and rate limiting policies"
  section_8: "Highlight API gateway, load balancer, and reverse proxy components"
  section_12: "Include OWASP API Security Top 10 and TLS enforcement"
---

# Web API Analysis Skill Pack

## Overview

This skill pack enriches BRD generation for repositories that expose HTTP or gRPC APIs.
It extracts endpoint contracts, authentication patterns, middleware chains, and API design
conventions that the standard pipeline's module-level analysis cannot detect.

## When This Skill Activates

- `evidence.has_http_api == True` or `evidence.has_grpc == True`
- Detected dependencies include any web framework (FastAPI, Express, Spring, etc.)
- File tree contains route/controller directories or `.proto` definition files
- Swagger/OpenAPI specification files are present

## Extraction Scripts

### Script 1: API Contract Extraction

Extracts all HTTP endpoints (method + path + handler) and gRPC service definitions.

```bash
python scripts/api_extractor.py <repo_dir> <output.json> contracts
```

**Output schema:**
```json
{
  "endpoints": [
    {"method": "GET", "path": "/api/users", "handler": "get_users", "source_file": "routes/users.py"}
  ],
  "total_endpoints": 12
}
```

### Script 2: Authentication Pattern Detection

Identifies auth mechanisms used in the codebase.

```bash
python scripts/api_extractor.py <repo_dir> <output.json> auth
```

**Output schema:**
```json
{
  "auth_type": "jwt",
  "auth_signals": ["@login_required", "Bearer token", "jwt.decode"],
  "features": [
    {"name": "JWT Authentication", "description": "Token-based authentication using JSON Web Tokens", "confidence": 0.9}
  ]
}
```

### Script 3: Middleware & Error Handling

Detects middleware chains and error handling patterns.

```bash
python scripts/api_extractor.py <repo_dir> <output.json> middleware
```

## How Results Are Used

- `contracts` output → merged into features as "API Surface" capability
- `auth` output → enhances NFR generation with specific security requirements
- Both → injected into BRD Section 5 (Functional Requirements) and Section 12 (Compliance)

## Common Mistakes

- Do NOT extract framework boilerplate routes (`/health`, `/metrics`, `/docs`) as business features
- Do NOT invent auth flows not evidenced in source code
- If repo has both REST and gRPC, run ALL subcommands and merge results

## Fallback Behavior

If scripts fail, log warning and continue pipeline with standard feature extraction.
This skill is enhancement-only, never blocking.
