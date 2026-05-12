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
    ptype = biz.get("product_type", "Software System")
    core_value = biz.get("core_value", "Provides core system functionality and data management.")
    summary = biz.get("product_summary", "A modern enterprise application.")
    caps = biz.get("core_capabilities", [])
    
    high_feats = [f for f in features if float(f.get("confidence", 0)) >= 0.8]
    low_feats = [f for f in features if float(f.get("confidence", 0)) < 0.6]

    caps_str = ", ".join(caps) if caps else "General operations, Data processing, and User management"

    exec_summary = (
        f"## 1. Executive Summary\n\n"
        f"This Business Requirements Document (BRD) specifies the functional, non-functional, and technical "
        f"requirements for the **{ptype}**. Based on comprehensive static analysis, the system encompasses "
        f"**{len(features)} functional domains**, of which **{len(high_feats)}** have been identified as high-confidence core capabilities. "
        f"{core_value}\n\n"
        f"**System Overview:**\n{summary}\n\n"
        f"**Core Capabilities:**\n- " + "\n- ".join(caps if caps else ["Core system functionality"]) + "\n\n"
    )

    if low_feats:
        exec_summary += (
            "**Areas Requiring Review:**\n"
            "The following modules exhibited low confidence during static analysis and may require further architectural discovery:\n"
        )
        for f in low_feats[:3]:
            exec_summary += f"- **{_display(f.get('name',''))}**: {f.get('description', 'Requires review.')}\n"

    exec_summary += "\n---\n"
    return exec_summary


def _s2_business_context(biz: Dict, features: List[Dict]) -> str:
    ptype = biz.get("product_type", "Software System")
    high_feats = [_display(f.get("name","")) for f in features if float(f.get("confidence",0)) >= 0.8]

    in_scope = "\n".join(f"- {c}" for c in (high_feats or ["Core application functionality", "Data persistence", "API routing"])[:8])
    out_scope = (
        "- Legacy system data migration (unless explicitly scripted)\n"
        "- Third-party vendor platform modifications\n"
        "- End-user hardware provisioning\n"
    )
    
    problem_stmt = "The current system requires formal specification and modernization to ensure scalability, maintainability, and alignment with enterprise architecture standards."

    goals_rows = "| G-01 | Architecture Modernization | Ensure all components align with current target architecture |\n"
    goals_rows += "| G-02 | Code Quality & Coverage | Achieve >80% automated test coverage across core modules |\n"
    
    if _has_keyword("auth", [f.get("name","") for f in features]):
        goals_rows += "| G-03 | Security Hardening | Secure authentication and authorization boundaries |\n"
    else:
        goals_rows += "| G-03 | Performance Optimization | Ensure response times meet enterprise SLAs |\n"
        
    goals_rows += "| G-04 | CI/CD Automation | Establish zero-touch deployment pipelines |\n"

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
    artifacts = biz.get("enterprise_artifacts", {})
    if artifacts and "stakeholders" in artifacts and artifacts["stakeholders"]:
        rows = ""
        for s in artifacts["stakeholders"]:
            rows += f"| {s.get('role','')} | {s.get('responsibility','')} | {s.get('impact','High')} |\n"
    else:
        users = biz.get("primary_users", ["System Administrators", "End Users"])
        rows = ""
        for u in users:
            rows += f"| {u} | Primary Actor | High |\n"
        rows += "| Engineering Lead | Architecture & Implementation | High |\n"
        rows += "| Product Owner | Requirement Validation | High |\n"
        rows += "| DevOps / SRE | Infrastructure & Operations | Medium |\n"

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

def _s5_functional_reqs(features: List[Dict], frs: List[Dict]) -> str:
    if not frs:
        return "## 5. Functional Requirements\n\n_No functional requirements detected._\n\n---\n"

    lines = [
        "## 5. Functional Requirements\n\n"
        "Requirements are categorized by their originating architectural feature. Priorities are assigned based on empirical confidence signals.\n"
    ]

    feat_conf = {f.get("name",""): float(f.get("confidence",0)) for f in features}
    feat_desc = {f.get("name",""): f.get("description", "") for f in features}
    fr_by_feat: Dict[str, List[Dict]] = {}
    
    for fr in frs:
        lf = fr.get("linked_feature", fr.get("mapped_feature", "unknown"))
        fr_by_feat.setdefault(lf, []).append(fr)

    for feat_name, feat_frs in fr_by_feat.items():
        display = _display(feat_name)
        conf = feat_conf.get(feat_name, 0.7)
        priority = _moscow(conf)
        desc = feat_desc.get(feat_name, "")
        
        lines.append(f"\n### 5.x Feature: {display}\n")
        lines.append(f"**Context:** {desc}\n")
        
        fr_table = "| ID | Requirement | Priority | Verification |\n|---|---|---|---|\n"
        for fr in feat_frs:
            fr_id = fr.get('id', 'FR-?')
            fr_desc = fr.get('description', '')
            fr_table += f"| **{fr_id}** | {fr_desc} | {priority} | Automated Test |\n"
            
            criteria = fr.get("acceptance_criteria", [])
            if criteria:
                fr_table += f"| | *AC:* {criteria[0]} | | |\n"
                
        lines.append(fr_table)

    lines.append("\n### Proposed Integration Interfaces\n")
    lines.append("For modules exposing APIs or remote procedures, the following standard RESTful signatures are recommended:\n")
    lines.append("| Resource | Method | Endpoint Path | Purpose |\n|---|---|---|---|")
    
    resource_feats = [f for f in features if "routing" not in f.get("name", "").lower()]
    for f in (resource_feats[:8] if resource_feats else features[:8]):
        path = _rest_path(f.get("name","resource"))
        lines.append(f"| {_display(f.get('name',''))} | GET | `/api/v1{path}` | Retrieve state/data |")
        lines.append(f"| {_display(f.get('name',''))} | POST | `/api/v1{path}` | Mutate state/data |")

    lines.append("\n---\n")
    return "\n".join(lines)


def _s6_nfrs(nfrs: List[Dict]) -> str:
    if not nfrs:
        return "## 6. Non-Functional Requirements\n\n_No NFRs detected._\n\n---\n"

    cats: Dict[str, List[Dict]] = {}
    for nfr in nfrs:
        cat = nfr.get("category", "General").capitalize()
        cats.setdefault(cat, []).append(nfr)

    lines = [
        "## 6. Non-Functional Requirements\n\n"
        "Non-functional constraints dictating system qualities.\n"
    ]
    
    for cat, items in sorted(cats.items()):
        lines.append(f"\n### 6.x {cat} Requirements\n")
        table = "| ID | Description | Target / SLA |\n|---|---|---|\n"
        for nfr in items:
            table += f"| **{nfr.get('id','NFR-?')}** | {nfr.get('description','')} | Strict |\n"
        lines.append(table)

    lines.append("\n---\n")
    return "\n".join(lines)


def _s7_data_requirements(features: List[Dict], tech_stack: List[str], biz: Dict) -> str:
    artifacts = biz.get("enterprise_artifacts", {})
    if artifacts and "data_requirements" in artifacts and artifacts["data_requirements"]:
        rows = ""
        for r in artifacts["data_requirements"]:
            rows += f"| {r.get('requirement','')} | {r.get('specification','')} |\n"
        return (
            "## 7. Data Requirements\n\n"
            "### 7.1 Database & Persistence Strategy\n\n"
            "| Requirement | Specification |\n|---|---|\n"
            f"{rows}\n\n"
            "### 7.2 Data Retention & Compliance\n\n"
            "- **PII Data**: Encrypted at rest (AES-256). Subject to GDPR right-to-erasure workflows.\n"
            "- **Application Logs**: Hot storage for 30 days, cold archive for 1 year.\n"
            "- **Secrets**: No secrets or API keys stored in plain text databases.\n\n---\n"
        )
        
    # Fallback deterministic generation
    has_sql = _has_keyword("sql", tech_stack) or _has_keyword("postgres", tech_stack) or _has_keyword("mysql", tech_stack)
    has_nosql = _has_keyword("mongo", tech_stack) or _has_keyword("redis", tech_stack)
    
    storage_type = "Relational (SQL) and/or Document storage"
    if has_sql and not has_nosql:
        storage_type = "Relational (SQL) database schema"
    elif has_nosql and not has_sql:
        storage_type = "NoSQL/Document store"
        
    schema_note = (
        "| Requirement | Specification |\n|---|---|\n"
        f"| Storage Paradigm | {storage_type} based on tech stack analysis. |\n"
        "| Data Integrity | ACID compliance for billing/auth; Eventual consistency acceptable for feeds/logs. |\n"
        "| Backup Strategy | Daily automated snapshots with 30-day retention and point-in-time recovery (PITR). |\n"
        "| Data Auditing | Append-only audit logs for all mutations to domain entities. |\n"
        "| Soft Deletion | Records SHALL utilize `deleted_at` timestamps to prevent accidental data loss. |\n"
    )

    return (
        "## 7. Data Requirements\n\n"
        "### 7.1 Database & Persistence Strategy\n\n"
        f"{schema_note}\n\n"
        "### 7.2 Data Retention & Compliance\n\n"
        "- **PII Data**: Encrypted at rest (AES-256). Subject to GDPR right-to-erasure workflows.\n"
        "- **Application Logs**: Hot storage for 30 days, cold archive for 1 year.\n"
        "- **Secrets**: No secrets or API keys stored in plain text databases.\n\n---\n"
    )


def _s8_tech_stack(biz: Dict) -> str:
    tech_stack = biz.get("tech_stack", [])
    
    if not tech_stack:
        return (
            "## 8. Technology Stack (TO-BE)\n\n"
            "_Technology stack was not explicitly detected. Standard enterprise cloud-native defaults apply._\n\n---\n"
        )
        
    rows = ""
    for tech in tech_stack:
        rows += f"| {tech} | Confirmed | Latest Stable / LTS |\n"
        
    return (
        "## 8. Technology Stack (TO-BE)\n\n"
        "| Component / Technology | Status | Target Version |\n"
        "|---|---|---|\n"
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

def _s10_infra(tech_stack: List[str], biz: Dict) -> str:
    orchestration = "Managed Kubernetes (EKS / GKE / AKS) or Serverless Containers"
    if _has_keyword("docker", tech_stack): orchestration = "Docker Containers"
    if _has_keyword("kubernetes", tech_stack) or _has_keyword("k8s", tech_stack): orchestration = "Kubernetes Cluster"
    if _has_keyword("serverless", tech_stack) or _has_keyword("lambda", tech_stack): orchestration = "Serverless Functions"

    artifacts = biz.get("enterprise_artifacts", {})
    if artifacts and "infrastructure" in artifacts and artifacts["infrastructure"]:
        rows = ""
        for r in artifacts["infrastructure"]:
            rows += f"| {r.get('aspect','')} | {r.get('specification','')} |\n"
    else:
        rows = (
            "| High Availability | Minimum 2 replicas/instances deployed across multiple availability zones. |\n"
            "| Auto-scaling | HPA / Auto-scaling groups configured based on CPU/Memory utilization thresholds (target ~70%). |\n"
            "| Load Balancing | Layer 7 Application Load Balancer with SSL termination. |\n"
            "| Observability | Centralized logging, distributed tracing, and metric scraping (e.g., OpenTelemetry, Prometheus). |\n"
            "| Secret Management | Runtime secret injection via Vault or Cloud Secret Manager. |\n"
        )

    return (
        "## 10. Infrastructure Requirements\n\n"
        f"**Target Architecture:** Cloud-Native / {orchestration}\n\n"
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

def _s12_compliance(biz: Dict) -> str:
    artifacts = biz.get("enterprise_artifacts", {})
    if artifacts and "compliance" in artifacts and artifacts["compliance"]:
        rows = ""
        for r in artifacts["compliance"]:
            rows += f"| {r.get('domain','')} | {r.get('requirement','')} | {r.get('strategy','')} |\n"
    else:
        rows = (
            "| Data Privacy (GDPR/CCPA) | Protection of Personally Identifiable Information (PII) | Encryption at rest, Data anonymization, Consent tracking. |\n"
            "| Security (OWASP) | Defense against top web vulnerabilities | SAST/DAST in pipelines, strict input validation, parameterized queries. |\n"
            "| Auditability | Traceability of administrative actions | Immutable audit logs for all destructive operations. |\n"
            "| Network Security | Secure data transit | TLS 1.3 enforcement on all external endpoints. |\n"
        )
        
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

def _s14_roadmap() -> str:
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

    rows = "\n".join(f"| OI-{i:02d} | {issue} | Open |" for i, issue in enumerate(issues, 1))
    return (
        "## 15. Open Issues & Decisions Required\n\n"
        "| ID | Issue | Status |\n|---|---|---|\n"
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

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compose_brd(
    business_context: Dict,
    features: List[Dict],
    functional_requirements: List[Dict],
    non_functional_requirements: List[Dict],
) -> str:
    today = date.today().strftime("%B %d, %Y")
    tech_stack = business_context.get("tech_stack", [])
    
    sections = [
        _cover(business_context, today),
        _s1_exec_summary(business_context, features),
        _s2_business_context(business_context, features),
        _s3_current_state(business_context, features),
        _s4_stakeholders(business_context),
        _s5_functional_reqs(features, functional_requirements),
        _s6_nfrs(non_functional_requirements),
        _s7_data_requirements(features, tech_stack, business_context),
        _s8_tech_stack(business_context),
        _s9_cicd(tech_stack, business_context),
        _s10_infra(tech_stack, business_context),
        _s11_risks(features, business_context),
        _s12_compliance(business_context),
        _s13_acceptance(),
        _s14_roadmap(),
        _s15_open_issues(business_context, features),
        _s16_approval(today),
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
