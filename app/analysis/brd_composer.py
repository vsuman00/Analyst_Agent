"""
brd_composer.py — Enterprise BRD Composer (16-section)
Produces a professional BRD matching industry standard structure.
"""
from __future__ import annotations
import json, argparse, sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _moscow(confidence: float) -> str:
    if confidence >= 0.8: return "Must Have"
    if confidence >= 0.6: return "Should Have"
    return "Could Have"

def _display(name: str) -> str:
    return name.replace("_", " ").title()

def _rest_path(name: str) -> str:
    return "/" + name.lower().replace(" ", "-").replace("_", "-")

def _has_keyword(keyword: str, text_list: List[str]) -> bool:
    return any(keyword.lower() in t.lower() for t in text_list)

# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _cover(biz: Dict, today: str) -> str:
    repo = biz.get("repo_name", "Enterprise System")
    ptype = biz.get("product_type", "Software Application")
    return (
        f"# BUSINESS REQUIREMENTS DOCUMENT (BRD)\n\n"
        f"**Project / Repository:** {repo}  \n"
        f"**System Archetype:** {ptype}  \n"
        f"**Document Version:** 1.0 — Final  \n"
        f"**Date:** {today}  \n"
        f"**Status:** Formal Review  \n\n---\n\n"
        "## Table of Contents\n\n"
        "1. Executive Summary\n"
        "2. Business Context & Objectives\n"
        "3. Current State Analysis (AS-IS)\n"
        "4. Stakeholders & Personas\n"
        "5. Functional Requirements\n"
        "6. Non-Functional Requirements\n"
        "7. Data Requirements\n"
        "8. Technology Stack (TO-BE)\n"
        "9. CI/CD Pipeline Requirements\n"
        "10. Infrastructure Requirements\n"
        "11. Risk Register\n"
        "12. Compliance & Legal\n"
        "13. Acceptance Criteria\n"
        "14. Delivery Roadmap\n"
        "15. Open Issues & Decisions\n"
        "16. Document Approval\n\n---\n"
    )

def _s1_exec_summary(biz: Dict, features: List[Dict]) -> str:
    # Use LLM-enriched executive summary if available
    enriched = biz.get("enriched_exec_summary", "")
    if enriched:
        return f"## 1. Executive Summary\n\n{enriched}\n\n---\n"

    # Deterministic fallback
    ptype = biz.get("product_type", "Software System")
    core_value = biz.get("core_value", "Provides core system functionality and data management.")
    summary = biz.get("product_summary", "A modern enterprise application.")
    caps = biz.get("core_capabilities", [])
    high_feats = [f for f in features if float(f.get("confidence", 0)) >= 0.8]
    low_feats  = [f for f in features if float(f.get("confidence", 0)) < 0.6]

    out = (
        f"## 1. Executive Summary\n\n"
        f"This Business Requirements Document (BRD) specifies the functional, non-functional, and technical "
        f"requirements for the **{ptype}**. Based on comprehensive static analysis, the system encompasses "
        f"**{len(features)} functional domains**, of which **{len(high_feats)}** have been identified as "
        f"high-confidence core capabilities. {core_value}\n\n"
        f"**System Overview:**\n{summary}\n\n"
        f"**Core Capabilities:**\n- " + "\n- ".join(caps or ["Core system functionality"]) + "\n\n"
    )
    if low_feats:
        out += "**Areas Requiring Review:**\n"
        for f in low_feats[:3]:
            out += f"- **{_display(f.get('name',''))}**: {f.get('description', 'Requires review.')}\n"
    out += "\n---\n"
    return out


def _s2_business_context(biz: Dict, features: List[Dict]) -> str:
    # Use LLM-enriched content when available
    problem_stmt = biz.get("enriched_problem_statement", "")
    enriched_goals = biz.get("enriched_goals", [])
    enriched_in  = biz.get("enriched_in_scope", [])
    enriched_out = biz.get("enriched_out_of_scope", [])

    if not problem_stmt:
        problem_stmt = "The current system requires formal specification and modernization to ensure scalability, maintainability, and alignment with enterprise architecture standards."

    # Goals table
    if enriched_goals:
        goals_rows = "".join(
            f"| {g.get('id','G-?')} | {g.get('goal','')} | {g.get('success_metric','')} |\n"
            for g in enriched_goals
        )
    else:
        ptype = biz.get("product_type", "Software System")
        goals_rows = "| G-01 | Architecture Modernization | Ensure all components align with current target architecture |\n"
        goals_rows += "| G-02 | Code Quality & Coverage | Achieve >80% automated test coverage across core modules |\n"
        goals_rows += (
            "| G-03 | Security Hardening | Secure authentication and authorization boundaries |\n"
            if _has_keyword("auth", [f.get("name","") for f in features])
            else "| G-03 | Performance Optimization | Ensure response times meet enterprise SLAs |\n"
        )
        goals_rows += "| G-04 | CI/CD Automation | Establish zero-touch deployment pipelines |\n"

    # Scope
    if enriched_in:
        in_scope = "\n".join(f"- {i}" for i in enriched_in)
    else:
        high_feats = [_display(f.get("name","")) for f in features if float(f.get("confidence",0)) >= 0.8]
        in_scope = "\n".join(f"- {c}" for c in (high_feats or ["Core application functionality", "Data persistence", "API routing"])[:8])

    if enriched_out:
        out_scope = "\n".join(f"- {o}" for o in enriched_out)
    else:
        out_scope = (
            "- Legacy system data migration (unless explicitly scripted)\n"
            "- Third-party vendor platform modifications\n"
            "- End-user hardware provisioning"
        )

    return (
        f"## 2. Business Context & Objectives\n\n"
        f"### 2.1 Business Problem Statement\n\n"
        f"{problem_stmt}\n\n"
        f"### 2.2 Project Goals\n\n"
        f"| # | Goal | Success Metric |\n|---|---|---|\n{goals_rows}\n"
        f"### 2.3 Project Scope\n\n"
        f"#### In Scope\n\n{in_scope}\n\n"
        f"#### Out of Scope\n\n{out_scope}\n\n---\n"
    )

def _s3_current_state(biz: Dict, features: List[Dict]) -> str:
    ptype = biz.get("product_type", "Software System")

    inv_rows = ""
    domain_rows = ""
    
    for f in features:
        name = f.get('name', '')
        desc = f.get('description', '')
        conf = float(f.get('confidence', 0))
        
        # Determine Layer
        layer = "Application Layer"
        if "api" in name or "routing" in name or "controller" in name:
            layer = "API / Routing Layer"
        elif "db" in name or "database" in name or "data" in name or "repo" in name:
            layer = "Data Access Layer"
        elif "service" in name or "logic" in name:
            layer = "Domain Service Layer"
        elif "ui" in name or "frontend" in name or "view" in name:
            layer = "Presentation Layer"
        elif "auth" in name or "security" in name:
            layer = "Security Layer"
        elif "test" in name:
            layer = "Testing Suite"
            
        inv_rows += f"| {layer} | {_display(name)} | {conf:.0%} |\n"
        
        # Collect Domain Entities
        if "entity" in name or "model" in name or "management" in name or "system" in name:
            domain_rows += f"| {_display(name)} | Core Entity / Subsystem | {desc.split('.')[0]} |\n"

    if not inv_rows:
        inv_rows = "| Core Module | Generic Component | 100% |\n"
    if not domain_rows:
        domain_rows = "| System Object | Generic Entity | Represents core state |\n"

    return (
        f"## 3. Current State Analysis (AS-IS)\n\n"
        f"### 3.1 Architecture Overview\n\n"
        f"The {ptype} comprises multiple functional boundaries mapped during static analysis.\n\n"
        f"| Layer / Component | Detected Module | Confidence |\n|---|---|---|\n{inv_rows}\n"
        f"### 3.2 Domain Entity Catalogue\n\n"
        f"| Entity / Domain | Type | Description |\n|---|---|---|\n{domain_rows}\n"
        f"---\n"
    )


def _s4_stakeholders(biz: Dict) -> str:
    # Priority: enriched → enterprise_artifacts → deterministic fallback
    enriched_stakes = biz.get("enriched_stakeholders", [])
    enriched_personas = biz.get("enriched_personas", [])

    artifacts = biz.get("enterprise_artifacts", {})
    artifact_stakes = artifacts.get("stakeholders", []) if artifacts else []

    stake_source = enriched_stakes or artifact_stakes
    if stake_source:
        rows = "".join(
            f"| {s.get('role','')} | {s.get('responsibility','')} | {s.get('impact','High')} |\n"
            for s in stake_source
        )
    else:
        users = biz.get("primary_users", ["System Administrators", "End Users"])
        rows = "".join(f"| {u} | Primary Actor | High |\n" for u in users)
        rows += "| Engineering Lead | Architecture & Implementation | High |\n"
        rows += "| Product Owner | Requirement Validation | High |\n"
        rows += "| DevOps / SRE | Infrastructure & Operations | Medium |\n"

    # Personas
    if enriched_personas:
        persona_rows = ""
        for i, p in enumerate(enriched_personas[:4], 1):
            persona_rows += (
                f"#### Persona {i} — {p.get('name', 'Stakeholder')}\n"
                f"- **Goal:** {p.get('goal', 'N/A')}\n"
                f"- **Pain Point:** {p.get('pain_point', 'N/A')}\n"
                f"- **Technical Literacy:** {p.get('technical_literacy', 'Medium')}\n"
                f"- **Needs from System:** {p.get('needs', 'N/A')}\n\n"
            )
    else:
        users = biz.get("primary_users", ["System Administrators", "End Users"])
        persona_rows = ""
        for i, u in enumerate(users[:3], 1):
            persona_rows += (
                f"#### Persona {i} — {u}\n"
                f"- **Role:** Interacts with the system to fulfill business workflows.\n"
                f"- **Needs:** High availability, data integrity, and intuitive interfaces.\n"
                f"- **Pain Points:** Complex navigation, slow response times.\n\n"
            )

    return (
        f"## 4. Stakeholders & Personas\n\n"
        f"### 4.1 Stakeholder Matrix\n\n"
        f"| Role | Responsibility | Impact |\n|---|---|---|\n{rows}\n"
        f"### 4.2 User Personas\n\n{persona_rows}---\n"
    )

def _s5_functional_reqs(features: List[Dict], frs: List[Dict], biz: Dict, evidence: Dict = None) -> str:
    if not frs:
        return "## 5. Functional Requirements\n\n_No functional requirements detected._\n\n---\n"

    biz = biz or {}
    evidence = evidence or {}
    enriched_frs = biz.get("enriched_frs", {})  # dict keyed by FR id

    lines = [
        "## 5. Functional Requirements\n\n"
        "Requirements are categorized by their originating architectural feature. "
        "Each requirement is presented in plain English first, followed by the precise technical specification.\n"
    ]

    feat_conf = {f.get("name",""): float(f.get("confidence",0)) for f in features}
    feat_desc = {f.get("name",""): f.get("description", "") for f in features}
    fr_by_feat: Dict[str, List[Dict]] = {}
    for fr in frs:
        lf = fr.get("linked_feature", fr.get("mapped_feature", "unknown"))
        fr_by_feat.setdefault(lf, []).append(fr)

    for feat_name, feat_frs in fr_by_feat.items():
        display  = _display(feat_name)
        conf     = feat_conf.get(feat_name, 0.7)
        priority = _moscow(conf)
        desc     = feat_desc.get(feat_name, "")

        lines.append(f"\n### 5.x Feature: {display}\n")
        lines.append(f"**What this feature does:** {desc}\n")

        fr_table = "| ID | Plain English | Technical Specification | Business Impact | Priority |\n|---|---|---|---|---|\n"
        for fr in feat_frs:
            fr_id   = fr.get('id', 'FR-?')
            e       = enriched_frs.get(fr_id, {})
            plain   = e.get("plain_english", fr.get('description', ''))
            tech    = e.get("technical_note", fr.get('description', ''))
            impact  = e.get("business_impact", "Required for system operation.")
            fr_table += f"| **{fr_id}** | {plain} | {tech} | {impact} | {priority} |\n"
            criteria = e.get("acceptance_criteria", fr.get("acceptance_criteria", []))
            if criteria:
                fr_table += f"| | *Verified by:* {criteria[0]} | | | |\n"
        lines.append(fr_table)

    lines.append("\n### Proposed Integration Interfaces\n")

    actual_endpoints = (evidence or {}).get("actual_endpoints", [])
    has_grpc         = (evidence or {}).get("has_grpc", False)
    has_http_api     = (evidence or {}).get("has_http_api", False)

    if actual_endpoints:
        # Use REAL extracted endpoints from the repo — never invent paths
        lines.append("The following HTTP endpoints were extracted from the repository source code:\n")
        lines.append("| Handler | Method | Endpoint Path | Source File |\n|---|---|---|---|")
        for ep in actual_endpoints[:12]:  # cap at 12 to keep BRD readable
            lines.append(
                f"| `{ep.get('handler','')}` "
                f"| **{ep.get('method','')}** "
                f"| `{ep.get('path','')}` "
                f"| {ep.get('source_file','')} |"
            )
    elif has_grpc:
        grpc_rpcs = (evidence or {}).get("grpc_rpcs", [])
        lines.append("This service uses **gRPC** for inter-service communication (`.proto` files detected).\n")
        if grpc_rpcs:
            lines.append("| Service | RPC | Request | Response | Source File |\n|---|---|---|---|---|")
            for rpc in grpc_rpcs[:8]:
                lines.append(
                    f"| `{rpc.get('service','')}` "
                    f"| `{rpc.get('rpc','')}` "
                    f"| `{rpc.get('request','')}` "
                    f"| `{rpc.get('response','')}` "
                    f"| {rpc.get('source_file','')} |"
                )
    elif not has_http_api:
        # No API evidence detected — do not invent REST paths
        lines.append(
            "_No HTTP API routes or gRPC definitions were detected in this repository. "
            "If REST endpoints are required, add them as an Open Issue in Section 15._"
        )
    else:
        lines.append("_API routes detected but could not be statically extracted. Review source for endpoint definitions._")

    lines.append("\n---\n")
    return "\n".join(lines)


def _s6_nfrs(nfrs: List[Dict], biz: Dict = None) -> str:
    if not nfrs:
        return "## 6. Non-Functional Requirements\n\n_No NFRs detected._\n\n---\n"

    biz = biz or {}
    enriched_nfrs = biz.get("enriched_nfrs", {})  # keyed by NFR id

    cats: Dict[str, List[Dict]] = {}
    for nfr in nfrs:
        cat = nfr.get("category", "General").capitalize()
        cats.setdefault(cat, []).append(nfr)

    lines = [
        "## 6. Non-Functional Requirements\n\n"
        "Non-functional constraints dictating system quality. Each requirement includes a plain English explanation "
        "and a specific, measurable target.\n"
    ]
    for cat, items in sorted(cats.items()):
        lines.append(f"\n### 6.x {cat} Requirements\n")
        table = "| ID | What This Means | Technical Target | Business Consequence |\n|---|---|---|---|\n"
        for nfr in items:
            nfr_id = nfr.get('id', 'NFR-?')
            e = enriched_nfrs.get(nfr_id, {})
            plain  = e.get("plain_english", nfr.get('description', ''))
            target = e.get("specific_target", "Strict — to be defined during discovery")
            impact = e.get("business_consequence", "Degraded user experience or system failure.")
            table += f"| **{nfr_id}** | {plain} | {target} | {impact} |\n"
        lines.append(table)

    lines.append("\n---\n")
    return "\n".join(lines)


def _s7_data_requirements(
    features: List[Dict],
    tech_stack: List[str],
    biz: Dict,
    evidence: Dict = None,
) -> str:
    evidence = evidence or {}
    artifacts = biz.get("enterprise_artifacts", {})

    # Determine real DB type from evidence, not generic tech_stack keyword search
    db_deps = evidence.get("dep_categories", {}).get("database", [])
    has_database = evidence.get("has_database", False)
    has_gdpr     = evidence.get("has_gdpr_mention", False)

    if not has_database and not db_deps:
        # No database detected — do not write a full DB strategy section
        return (
            "## 7. Data Requirements\n\n"
            "### 7.1 Database & Persistence Strategy\n\n"
            "_No database dependencies were detected in this repository. "
            "If persistent storage is required, specify the data store in Open Issues (Section 15)._\n\n"
            "### 7.2 Data Retention & Compliance\n\n"
            "_Data retention policy not applicable — no persistence layer detected._\n\n---\n"
        )

    # Build DB strategy from actual detected dependencies
    if db_deps:
        storage_type = ", ".join(db_deps[:3])
    elif _has_keyword("sql", tech_stack) or _has_keyword("postgres", tech_stack):
        storage_type = "Relational (SQL)"
    elif _has_keyword("mongo", tech_stack) or _has_keyword("redis", tech_stack):
        storage_type = "NoSQL / Document store"
    else:
        storage_type = "Relational database (inferred from framework)"

    if artifacts and "data_requirements" in artifacts and artifacts["data_requirements"]:
        rows = ""
        for r in artifacts["data_requirements"]:
            rows += f"| {r.get('requirement','')} | {r.get('specification','')} |\n"
    else:
        rows = (
            f"| Storage Paradigm | {storage_type} |\n"
            "| Data Integrity | ACID compliance for transactional data. |\n"
            "| Backup Strategy | Daily automated snapshots with 30-day retention. |\n"
            "| Data Auditing | Append-only audit logs for all mutations to domain entities. |\n"
            "| Soft Deletion | Records SHALL use `deleted_at` timestamps to prevent accidental loss. |\n"
        )

    # Only write GDPR/PII block if the repo itself mentions it
    if has_gdpr:
        compliance_block = (
            "### 7.2 Data Retention & Compliance\n\n"
            "- **PII Data**: Encrypted at rest (AES-256). Subject to GDPR right-to-erasure workflows "
            "(evidenced by compliance mention in repository documentation).\n"
            "- **Application Logs**: Hot storage for 30 days, cold archive for 1 year.\n"
            "- **Secrets**: No secrets or API keys stored in plain text.\n"
        )
    elif evidence.get("has_auth"):
        compliance_block = (
            "### 7.2 Data Retention & Compliance\n\n"
            "- **Credentials**: Hashed using a strong one-way function (e.g., bcrypt). Never stored in plain text.\n"
            "- **Session Tokens**: Short-lived; invalidated on logout.\n"
            "- **Secrets**: No secrets or API keys stored in plain text.\n"
        )
    else:
        compliance_block = (
            "### 7.2 Data Retention & Compliance\n\n"
            "_Data classification and retention policy requires manual definition. "
            "No PII or compliance signals were detected in the repository._\n"
        )

    return (
        "## 7. Data Requirements\n\n"
        "### 7.1 Database & Persistence Strategy\n\n"
        "| Requirement | Specification |\n|---|---|\n"
        f"{rows}\n\n"
        f"{compliance_block}\n---\n"
    )


def _s8_tech_stack(biz: Dict) -> str:
    tech_stack = biz.get("tech_stack", [])
    if not tech_stack:
        return (
            "## 8. Technology Stack (TO-BE)\n\n"
            "_Technology stack was not explicitly detected. Standard enterprise cloud-native defaults apply._\n\n---\n"
        )

    # Plain-English purpose for common technologies
    _purposes = {
        "python": "Primary programming language for backend logic",
        "java": "Primary programming language for backend services",
        "javascript": "Frontend and/or server-side scripting language",
        "typescript": "Typed superset of JavaScript for safer frontend/backend code",
        "go": "High-performance backend language",
        "rust": "Systems-level language for performance-critical components",
        "react": "User interface library for building interactive web pages",
        "spring": "Java framework for building web APIs and services",
        "fastapi": "Python framework for building web APIs",
        "django": "Python framework for building full-stack web applications",
        "postgres": "Relational database for structured data storage",
        "postgresql": "Relational database for structured data storage",
        "mysql": "Relational database for structured data storage",
        "mongodb": "Document database for flexible, schema-less data storage",
        "redis": "In-memory cache for fast data retrieval and session storage",
        "docker": "Containerisation tool — packages the app for consistent deployment",
        "kubernetes": "Container orchestration — manages deployment at scale",
        "kafka": "Message streaming platform for real-time data pipelines",
        "elasticsearch": "Search engine for fast full-text queries",
        "nginx": "Web server and reverse proxy for routing incoming traffic",
        "gradle": "Build automation tool for compiling and packaging code",
        "maven": "Build and dependency management tool for Java projects",
        "npm": "Package manager for JavaScript dependencies",
        "pip": "Package manager for Python dependencies",
    }

    rows = ""
    for tech in tech_stack:
        purpose = _purposes.get(tech.lower(), "Supporting technology component")
        rows += f"| {tech} | Confirmed | Latest Stable / LTS | {purpose} |\n"

    return (
        "## 8. Technology Stack (TO-BE)\n\n"
        "| Component / Technology | Status | Target Version | Purpose (Plain English) |\n"
        "|---|---|---|---|\n"
        f"{rows}\n---\n"
    )


def _s9_cicd(tech_stack: List[str], biz: Dict) -> str:
    tool = "Enterprise CI/CD Tool (e.g., GitHub Actions, GitLab CI)"
    if _has_keyword("github", tech_stack): tool = "GitHub Actions"
    if _has_keyword("gitlab", tech_stack): tool = "GitLab CI"
    if _has_keyword("jenkins", tech_stack): tool = "Jenkins"
    
    artifacts = biz.get("enterprise_artifacts", {})
    if artifacts and "cicd_standards" in artifacts and artifacts["cicd_standards"]:
        rows = ""
        for r in artifacts["cicd_standards"]:
            rows += f"| {r.get('id','')} | {r.get('standard','')} |\n"
    else:
        rows = (
            "| CI-01 | All code merged to `main` SHALL pass automated tests and static analysis. |\n"
            "| CI-02 | Build artifacts SHALL be immutable and uniquely versioned (e.g., Git SHA). |\n"
            "| CI-03 | Infrastructure provisioning SHALL be fully automated (IaC). |\n"
            "| CI-04 | Deployment rollback SHALL be executable within 5 minutes. |\n"
        )
        
    return (
        "## 9. CI/CD Pipeline Requirements\n\n"
        f"**Primary Orchestrator:** {tool}\n\n"
        "### 9.1 Pipeline Stages\n\n"
        "`Commit` → `Lint & SAST` → `Unit Tests` → `Build/Containerize` → `Integration Tests` → `Deploy to Staging` → `Manual Gate` → `Deploy to Prod`\n\n"
        "### 9.2 Release Standards\n\n"
        "| ID | Standard |\n|---|---|\n"
        f"{rows}\n---\n"
    )

def _s10_infra(tech_stack: List[str], biz: Dict, evidence: Dict = None) -> str:
    evidence = evidence or {}

    # Android and desktop apps don't have server infrastructure
    if evidence.get("has_android") or evidence.get("has_ios"):
        return (
            "## 10. Infrastructure Requirements\n\n"
            "**Target Architecture:** Mobile Application — No server infrastructure detected in this repository.\n\n"
            "| Resource Aspect | Specification |\n|---|---|\n"
            "| Deployment | Published via app store (Google Play / Apple App Store). |"
            " No server-side provisioning required unless a backend service is added. |\n"
            "| Backend API | Not evidenced. Define in Open Issues (Section 15) if a backend is needed. |\n"
            "\n---\n"
        )
    if evidence.get("has_desktop"):
        return (
            "## 10. Infrastructure Requirements\n\n"
            "**Target Architecture:** Desktop Application — Server infrastructure not applicable.\n\n"
            "| Resource Aspect | Specification |\n|---|---|\n"
            "| Distribution | Installer package (e.g., MSI, NSIS, pkg). |\n"
            "| Update Mechanism | To be defined. Requires manual specification. |\n"
            "\n---\n"
        )

    # For server/web apps — only claim what the repo has evidence for
    if evidence.get("has_kubernetes"):
        orchestration = "Kubernetes Cluster"
        infra_note = " (evidenced by k8s manifests / Deployment YAML files in repository)"
    elif evidence.get("has_docker"):
        orchestration = "Docker Containers"
        infra_note = " (evidenced by Dockerfile in repository)"
    elif _has_keyword("serverless", tech_stack) or _has_keyword("lambda", tech_stack):
        orchestration = "Serverless Functions"
        infra_note = ""
    else:
        # No infra evidence — do not invent cloud-native architecture
        return (
            "## 10. Infrastructure Requirements\n\n"
            "**Target Architecture:** Not evidenced — no container, cloud, or deployment configuration detected.\n\n"
            "| Resource Aspect | Specification |\n|---|---|\n"
            "| Deployment Target | Requires definition. No Dockerfile or infrastructure-as-code was detected. |\n"
            "| High Availability | To be defined based on chosen deployment target. |\n"
            "\n---\n"
        )

    artifacts = biz.get("enterprise_artifacts", {})
    if artifacts and "infrastructure" in artifacts and artifacts["infrastructure"]:
        rows = ""
        for r in artifacts["infrastructure"]:
            rows += f"| {r.get('aspect','')} | {r.get('specification','')} |\n"
    else:
        rows = (
            "| High Availability | Minimum 2 replicas deployed across availability zones. |\n"
            "| Auto-scaling | Configured based on CPU/Memory utilization thresholds. |\n"
            "| Load Balancing | Application Load Balancer with SSL termination. |\n"
            "| Observability | Centralized logging and metric collection. |\n"
            "| Secret Management | Runtime secret injection via secure vault. |\n"
        )

    return (
        "## 10. Infrastructure Requirements\n\n"
        f"**Target Architecture:** {orchestration}{infra_note}\n\n"
        "| Resource Aspect | Specification |\n|---|---|\n"
        f"{rows}\n---\n"
    )

def _s11_risks(features: List[Dict], biz: Dict) -> str:
    artifacts = biz.get("enterprise_artifacts", {})
    if artifacts and "risks" in artifacts and artifacts["risks"]:
        rows = ""
        for r in artifacts["risks"]:
            rows += f"| {r.get('id','')} | {r.get('description','')} | {r.get('probability','Medium')} | {r.get('impact','Medium')} | {r.get('mitigation','')} | Open |\n"
    else:
        rows = ""
        r_idx = 1
        low_feats = [f for f in features if float(f.get("confidence", 1)) < 0.6]
        for f in low_feats:
            rows += f"| R-{r_idx:02d} | Ambiguous Implementation: {_display(f.get('name',''))} | Medium | High | Conduct code-level discovery | Open |\n"
            r_idx += 1
        rows += f"| R-{r_idx:02d} | Legacy Dependencies | High | Medium | Execute automated vulnerability scans | Open |\n"
        r_idx += 1
        rows += f"| R-{r_idx:02d} | Test Coverage Deficiencies | Medium | High | Enforce branch coverage metrics | Open |\n"

    return (
        "## 11. Risk Register\n\n"
        "| ID | Risk Description | Probability | Impact | Mitigation Strategy | Status |\n"
        "|---|---|---|---|---|---|\n"
        f"{rows}\n---\n"
    )

def _s12_compliance(biz: Dict, evidence: Dict = None) -> str:
    evidence = evidence or {}
    has_http_api = evidence.get("has_http_api", False)
    has_auth     = evidence.get("has_auth", False)
    has_gdpr     = evidence.get("has_gdpr_mention", False)

    artifacts = biz.get("enterprise_artifacts", {})
    if artifacts and "compliance" in artifacts and artifacts["compliance"]:
        rows = ""
        for r in artifacts["compliance"]:
            rows += f"| {r.get('domain','')} | {r.get('requirement','')} | {r.get('strategy','')} |\n"
    elif not has_http_api and not has_auth and not has_gdpr:
        # No web, auth, or compliance evidence — do not invent GDPR/OWASP/TLS
        rows = (
            "| Compliance Scope | Not evidenced — no web endpoints, authentication, or data privacy signals detected. "
            "Requires manual definition based on deployment context. | Define in Open Issues (Section 15). |\n"
        )
    else:
        rows = ""
        if has_gdpr:
            rows += "| Data Privacy (GDPR/CCPA) | Protection of PII — evidenced by compliance mention in repository docs. | Encryption at rest, consent tracking. |\n"
        if has_auth:
            rows += "| Authentication Security | Secure credential storage and session management. | Password hashing, token expiry, rate limiting on auth endpoints. |\n"
        if has_http_api:
            rows += "| Security (OWASP) | Defense against common web vulnerabilities. | SAST/DAST in pipelines, input validation, parameterized queries. |\n"
            rows += "| Network Security | Secure data transit. | TLS enforcement on all external endpoints. |\n"
        rows += "| Auditability | Traceability of administrative actions. | Immutable audit logs for all destructive operations. |\n"

    return (
        "## 12. Compliance & Legal Requirements\n\n"
        "| Domain | Requirement | Implementation Strategy |\n|---|---|---|\n"
        f"{rows}\n---\n"
    )

def _s13_acceptance() -> str:
    return (
        "## 13. Acceptance Criteria\n\n"
        "### 13.1 Delivery Acceptance\n\n"
        "- **Functional:** 100% of Must-Have Functional Requirements (Section 5) pass QA validation.\n"
        "- **Non-Functional:** System demonstrates compliance with specified NFR SLAs (Section 6) under load testing.\n"
        "- **Defects:** Zero P0 (Critical) or P1 (High) defects exist at the time of release candidate branching.\n\n"
        "### 13.2 Operational Acceptance\n\n"
        "- CI/CD pipelines successfully deploy the application to a production-like staging environment.\n"
        "- Application metrics, logs, and alerts are verified in the centralized observability dashboard.\n"
        "- Disaster recovery (backup restoration) runbook is documented and successfully tested.\n\n---\n"
    )

def _s14_roadmap(biz: Dict = None) -> str:
    biz = biz or {}
    enriched_phases = biz.get("enriched_roadmap", [])
    if enriched_phases:
        rows = ""
        for p in enriched_phases:
            feats = ", ".join(p.get("features_delivered", [])[:4])
            risks = "; ".join(p.get("key_risks", [])[:2])
            rows += (
                f"| **Phase {p.get('number','?')}: {p.get('name','')}** "
                f"| {p.get('focus','')} "
                f"| {feats or 'See feature list'} "
                f"| {p.get('definition_of_done','')} "
                f"| {p.get('estimated_duration','TBD')} "
                f"| {risks or 'None identified'} |\n"
            )
        return (
            "## 14. Delivery Roadmap\n\n"
            "A phased delivery approach mapped to the detected features. Earlier phases deliver the highest-confidence capabilities first.\n\n"
            "| Phase | Business Focus | Key Features | Definition of Done | Est. Duration | Key Risks |\n"
            "|---|---|---|---|---|---|\n"
            f"{rows}\n---\n"
        )
    # Deterministic fallback
    return (
        "## 14. Delivery Roadmap\n\n"
        "A phased modernization and delivery approach.\n\n"
        "| Phase | Focus Area | Key Deliverables |\n|---|---|---|\n"
        "| **Phase 1: Foundation** | Infrastructure & CI/CD | Setup target environment, pipeline automation, and initial code migration. |\n"
        "| **Phase 2: Core Refactor** | Backend & Data Layer | Address low-confidence modules, optimize data schemas, implement missing FRs. |\n"
        "| **Phase 3: Hardening** | Security & Observability | Security audits, tracing integration, load testing. |\n"
        "| **Phase 4: Transition** | Cutover & Go-Live | UAT sign-off, production deployment, legacy deprecation. |\n\n---\n"
    )

def _s15_open_issues(biz: Dict, features: List[Dict]) -> str:
    enriched = biz.get("enriched_open_issues", [])
    if enriched:
        rows = "".join(
            f"| {i.get('id','OI-?')} | {i.get('question','')} | {i.get('owner','Both')} "
            f"| {i.get('business_impact','')} | {i.get('recommended_action','')} | {i.get('priority','Medium')} |\n"
            for i in enriched
        )
        return (
            "## 15. Open Issues & Decisions Required\n\n"
            "| ID | Open Question | Owner | Business Impact | Recommended Action | Priority |\n"
            "|---|---|---|---|---|---|\n"
            f"{rows}\n\n---\n"
        )

    # Deterministic fallback
    issues = []
    if len(features) < 5:
        issues.append("Low feature count detected; system boundaries may be incomplete or strictly microservice-scoped.")
    low = sum(1 for f in features if float(f.get("confidence", 1)) < 0.6)
    if low > 0:
        issues.append(f"{low} subsystems generated low confidence signals requiring manual review by lead engineers.")
    if not biz.get("tech_stack"):
        issues.append("Technical stack could not be fully resolved; infrastructure assumptions must be validated.")
    if not issues:
        issues.append("No immediate technical blockers identified from static analysis.")
    rows = "\n".join(f"| OI-{i:02d} | {issue} | Both | Undefined | Manual review | Medium |" for i, issue in enumerate(issues, 1))
    return (
        "## 15. Open Issues & Decisions Required\n\n"
        "| ID | Issue | Owner | Business Impact | Recommended Action | Priority |\n"
        "|---|---|---|---|---|---|\n"
        f"{rows}\n\n---\n"
    )

def _s16_approval(today: str) -> str:
    return (
        "## 16. Document Approval\n\n"
        "Signatures below indicate acceptance of the requirements outlined in this document.\n\n"
        "| Role | Name | Signature | Date |\n|---|---|---|---|\n"
        "| Business Sponsor | | | |\n"
        "| Product Owner | | | |\n"
        "| Engineering Lead | | | |\n"
        "| Security / Compliance | | | |\n\n"
        f"_Document generated deterministically via Analyst Agent on {today}._\n"
    )


def _s17_glossary(biz: Dict) -> str:
    glossary = biz.get("glossary_terms", {})
    if not glossary:
        return ""
    rows = "".join(
        f"| **{term}** | {defn} |\n"
        for term, defn in sorted(glossary.items())
    )
    return (
        "## 17. Glossary of Technical Terms\n\n"
        "This glossary explains technical terms used in this document in plain English, "
        "so that all stakeholders can read and understand the full document.\n\n"
        "| Term | Plain English Definition |\n|---|---|\n"
        f"{rows}\n---\n"
    )

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compose_brd(
    business_context: Dict,
    features: List[Dict],
    functional_requirements: List[Dict],
    non_functional_requirements: List[Dict],
    evidence: Dict = None,
) -> str:
    evidence   = evidence or {}
    today      = date.today().strftime("%B %d, %Y")
    tech_stack = business_context.get("tech_stack", [])

    # Update ToC if glossary terms exist
    cover = _cover(business_context, today)
    if business_context.get("glossary_terms"):
        cover = cover.replace(
            "16. Document Approval",
            "16. Document Approval\n17. Glossary of Technical Terms"
        )

    sections = [
        cover,
        _s1_exec_summary(business_context, features),
        _s2_business_context(business_context, features),
        _s3_current_state(business_context, features),
        _s4_stakeholders(business_context),
        _s5_functional_reqs(features, functional_requirements, business_context, evidence=evidence),
        _s6_nfrs(non_functional_requirements, business_context),
        _s7_data_requirements(features, tech_stack, business_context, evidence=evidence),
        _s8_tech_stack(business_context),
        _s9_cicd(tech_stack, business_context),
        _s10_infra(tech_stack, business_context, evidence=evidence),
        _s11_risks(features, business_context),
        _s12_compliance(business_context, evidence=evidence),
        _s13_acceptance(),
        _s14_roadmap(business_context),
        _s15_open_issues(business_context, features),
        _s16_approval(today),
        _s17_glossary(business_context),
    ]
    return "\n".join(sections)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BRDComposer: 16-section enterprise BRD.")
    parser.add_argument("--business-context", required=True)
    parser.add_argument("--features",         required=True)
    parser.add_argument("--functional",       required=True)
    parser.add_argument("--non-functional",   required=True)
    parser.add_argument("--out",              default=None)
    args = parser.parse_args()

    def _load(p: str):
        return json.load(open(p, encoding="utf-8"))

    biz  = _load(args.business_context)
    biz  = biz.get("business_context", biz)
    feat = _load(args.features)
    feat = feat.get("validated_features", feat.get("features", feat)) if isinstance(feat, dict) else feat
    fr   = _load(args.functional)
    fr   = fr.get("functional_requirements", fr) if isinstance(fr, dict) else fr
    nfr  = _load(args.non_functional)
    nfr  = nfr.get("non_functional_requirements", nfr) if isinstance(nfr, dict) else nfr

    md = compose_brd(biz, feat or [], fr or [], nfr or [])
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"[OK] BRD written to {args.out}", file=sys.stderr)
    else:
        print(md)
