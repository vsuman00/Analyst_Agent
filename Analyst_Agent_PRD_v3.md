# Analyst Agent --- PRD v3 (Enterprise + Prompts + Schemas + Execution Traces)

------------------------------------------------------------------------

# 1. Product Overview

Analyst Agent is an AI backend system that converts GitHub repositories
into enterprise-grade BRDs using deterministic analysis + multi-agent
reasoning.

------------------------------------------------------------------------

# 2. Final System Architecture

Client → FastAPI → Pipeline Controller → ECA → Context Builder →
Normalizer → Validator → Budget Manager → Agents → Business Layer →
Requirements → BRD → Validator → Export

------------------------------------------------------------------------

# 3. Pipeline State Machine

CREATED → INGESTING → ECA_DONE → CONTEXT_READY → NORMALIZED → VALIDATED
→ ANALYZED → BRD_READY → VALIDATING → IMPROVING → COMPLETED / FAILED

------------------------------------------------------------------------

# 4. Core Schemas

## 4.1 ECA Output

{ "readme": "string", "file_tree": {}, "classified_files": {}, "chunks":
\[\] }

## 4.2 Normalized Context

{ "features": \[ { "name": "Authentication", "confidence": 0.82,
"sources": \["auth.js"\] } \], "modules": \[\], "gaps": \[\] }

## 4.3 Feature Output

{ "features": \[ { "name": "","description": "","confidence": 0.0 } \] }

## 4.4 BRD Schema

{ "executive_summary": "","objectives": \[\], "personas": \[\],
"functional_requirements": \[\], "non_functional_requirements": \[\],
"risks": \[\] }

------------------------------------------------------------------------

# 5. Agent Prompts (Production Ready)

## 5.1 Repo Understanding Agent

System Prompt: You are a senior business analyst. Extract product
understanding from repository context.

User Input: \<README + metadata\>

Output: { "product_type": "","target_users": \[\], "value_proposition":
"" }

------------------------------------------------------------------------

## 5.2 Feature Extraction Agent

System Prompt: Extract concrete system features. Avoid assumptions
unless necessary.

Output: { "features": \[ { "name": "","description": "","confidence":
0.0 } \] }

------------------------------------------------------------------------

## 5.3 Persona Agent

System Prompt: Generate realistic personas based on system usage.

------------------------------------------------------------------------

## 5.4 Requirement Agent

System Prompt: Convert features into enterprise-grade functional
requirements.

Output: { "id": "FR-001", "description": "","priority": "High" }

------------------------------------------------------------------------

## 5.5 BRD Writer

System Prompt: Generate structured BRD. Avoid generic language.

------------------------------------------------------------------------

# 6. Validation Rules

-   No vague statements
-   Every requirement maps to feature
-   Persona must include pain points
-   Missing sections → fail

------------------------------------------------------------------------

# 7. Execution Trace Example

## Input

Repo: github.com/sample/project

## Trace

Step 1: Repo Clone - status: success - latency: 2.1s

Step 2: ECA Processing - files_processed: 120 - chunks: 340

Step 3: Context Normalization - features_detected: 6 - confidence_avg:
0.78

Step 4: Feature Extraction (LLM) - tokens_in: 3200 - tokens_out: 600

Step 5: BRD Generation - tokens_in: 4200 - tokens_out: 1500

Step 6: Validation - score: 0.83 → improvement triggered

Step 7: Final Output - score: 0.89 - file: brd_123.md

------------------------------------------------------------------------

# 8. Failure Handling

-   LLM timeout → retry (3x)
-   Missing README → infer from code
-   Large repo → reduce context

------------------------------------------------------------------------

# 9. Prompt Versioning

PROMPT_VERSION = "v3.0"

------------------------------------------------------------------------

# 10. Conclusion

This system is a production-grade AI pipeline with deterministic +
reasoning layers, validation, traceability, and scalability.
