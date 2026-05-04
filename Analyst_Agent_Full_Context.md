# Analyst Agent --- Full Context Documentation

## 1. System Overview

Analyst Agent is an AI backend system that converts GitHub repositories
into enterprise-grade Business Requirement Documents (BRDs).

------------------------------------------------------------------------

## 2. System Architecture

Client → FastAPI → Pipeline Controller → ECA Engine → Context Builder →
Context Normalizer → Context Validator → Context Budget Manager → LLM
Agents → Business Layer → Requirement Engine → BRD Composer → Validator
→ Document Builder → Output

------------------------------------------------------------------------

## 3. Full Pipeline Workflow

### Stage 1 --- ECA

-   Clone repo
-   Build file tree
-   Filter files
-   Classify files
-   Extract content
-   Chunk content

### Stage 2 --- Context

-   Aggregate data
-   Normalize features
-   Validate completeness
-   Apply token limits

### Stage 3 --- Intelligence (LLM)

-   Repo understanding
-   Feature extraction
-   User flows
-   Business logic
-   Personas

### Stage 4 --- Requirements

-   Functional requirements
-   Non-functional requirements
-   Risks

### Stage 5 --- BRD Generation

-   Structured document creation

### Stage 6 --- Validation

-   Score and improve output

------------------------------------------------------------------------

## 4. Design Principles

-   Separation of concerns
-   Structured JSON contracts
-   No raw code to LLM
-   Multi-step reasoning
-   Validation-first system

------------------------------------------------------------------------

## 5. ECA Strategy

Extract → Classify → Aggregate

Include: - README - src/ - routes/ - services/

Ignore: - node_modules - build - binaries

------------------------------------------------------------------------

## 6. Context Intelligence

-   Normalization
-   Validation
-   Token control

------------------------------------------------------------------------

## 7. Agent System

Agents: - Repo Agent - Feature Agent - Flow Agent - Business Agent -
Persona Agent - Requirement Agent - BRD Writer - Validator

------------------------------------------------------------------------

## 8. Validation System

Score threshold: 0.85

------------------------------------------------------------------------

## 9. Fix Loop

Generate → Validate → Improve

------------------------------------------------------------------------

## 10. Folder Structure

app/ ├── api/ ├── pipeline/ ├── eca/ ├── context/ ├── agents/ ├──
business/ ├── requirements/ ├── brd/ ├── validation/ ├── document/ ├──
utils/

------------------------------------------------------------------------

## 11. Risks

-   Large repos → token control
-   Missing README → infer
-   Hallucination → validation

------------------------------------------------------------------------

## 12. Next Steps

1.  Build ECA layer
2.  Add context normalizer
3.  Add first agents
4.  Generate BRD
