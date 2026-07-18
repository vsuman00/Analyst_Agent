# Project Constitution

## Data Schemas

### 1. ECA Output Schema
```json
{
  "readme": "string",
  "file_tree": {},
  "classified_files": {
    "frontend": ["string"],
    "backend": ["string"],
    "config": ["string"],
    "docs": ["string"],
    "unknown": ["string"]
  },
  "chunks": [
    {
      "file": "string",
      "content": "string"
    }
  ]
}
```

### 2. Normalized Context Schema
```json
{
  "features": [
    {
      "name": "string",
      "confidence": "number",
      "sources": ["string"]
    }
  ],
  "modules": ["string"],
  "gaps": ["string"]
}
```

## Behavioral Rules
1. **Reliability First**: Prioritize reliability over speed. Never guess at business logic.
2. **Data-First Rule**: The JSON Data Schema (Input/Output shapes) must be defined here before any coding begins.
3. **Self-Annealing (Repair Loop)**: When an error occurs: Analyze -> Patch -> Test -> Update Architecture `.md` file.
4. **Deliverables vs Intermediates**: `.tmp/` is for ephemeral files. The project is only complete when the payload reaches its final global/cloud destination.

## Architectural Invariants (A.N.T. 3-Layer Architecture)
- **Layer 1: Architecture (`architecture/`)**
  - Technical SOPs written in Markdown. If logic changes, update the SOP before updating code.
- **Layer 2: Navigation**
  - The reasoning layer. Route data between SOPs and Tools. No complex tasks performed directly by LLM.
- **Layer 3: Tools (`tools/`)**
  - Deterministic Python scripts. Atomic and testable.
  - Environment variables/tokens stored in `.env`.
  - All intermediate file operations in `.tmp/`.
