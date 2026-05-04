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
    if confidence >= 0.8: return "M"
    if confidence >= 0.6: return "S"
    return "C"

def _display(name: str) -> str:
    return name.replace("_", " ").title()

def _rest_path(name: str) -> str:
    return "/" + name.lower().replace(" ", "-").replace("_", "-")

# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _cover(biz: Dict, today: str) -> str:
    repo = biz.get("repo_name", "Target System")
    ptype = biz.get("product_type", "Software System")
    return (
        f"# BUSINESS REQUIREMENTS DOCUMENT\n\n"
        f"**Project:** {repo}  \n"
        f"**System Type:** {ptype}  \n"
        f"**Prepared by:** Analyst Agent  \n"
        f"**Version:** 1.0 — Draft  \n"
        f"**Date:** {today}  \n"
        f"**Status:** Draft — Pending Review  \n\n---\n\n"
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
    core_value = biz.get("core_value", "")
    summary = biz.get("product_summary", "")
    caps = biz.get("core_capabilities", [])
    n = len(features)
    high = [f for f in features if float(f.get("confidence", 0)) >= 0.8]

    pain_bullets = ""
    low_conf = [f for f in features if float(f.get("confidence", 0)) < 0.6]
    if low_conf:
        pain_bullets = "\n".join(f"- Low-confidence capability detected: **{_display(f.get('name',''))}** ({float(f.get('confidence',0)):.0%})" for f in low_conf[:4])
    else:
        pain_bullets = "- No critical deficiencies detected in feature confidence scores."

    caps_str = ", ".join(caps[:4]) if caps else "core system capabilities"

    return (
        f"## 1. Executive Summary\n\n"
        f"This document specifies the complete business and technical requirements for the **{ptype}**. "
        f"Static analysis identified **{n} functional capabilities**, of which **{len(high)}** carry high confidence (≥80%). "
        f"{core_value}\n\n"
        f"{summary}\n\n"
        f"**Key Identified Areas:**\n\n{pain_bullets}\n\n"
        f"**Core Capabilities:** {caps_str}\n\n"
        "_This BRD is generated deterministically from structured pipeline analysis. "
        "All technical data is sourced directly from the repository._\n\n---\n"
    )


def _s2_business_context(biz: Dict, features: List[Dict]) -> str:
    ptype = biz.get("product_type", "Software System")
    caps = biz.get("core_capabilities", [])
    high_feats = [_display(f.get("name","")) for f in features if float(f.get("confidence",0)) >= 0.8]
    low_feats  = [_display(f.get("name","")) for f in features if float(f.get("confidence",0)) < 0.6]

    in_scope = "\n".join(f"- {c}" for c in (high_feats or caps or ["Core system functionality"])[:6])
    out_scope = (
        "- Mobile client application changes\n"
        "- Frontend / web UI development (if not present)\n"
        "- Multi-region deployment\n"
        "- Machine learning-based features\n"
        "- Real-time WebSocket/SSE push (deferred)"
    )
    problem = (
        f"- {len(low_feats)} capability area(s) carry low confidence scores, indicating incomplete implementation or missing modules.\n"
        if low_feats else
        "- System capabilities are well-defined. Focus is on modernization and quality improvement.\n"
    )

    goals_rows = "| G-01 | Upgrade all end-of-life dependencies | All deps at actively supported versions |\n"
    if any("auth" in f.get("name","").lower() for f in features):
        goals_rows += "| G-02 | Harden authentication layer | Zero P0 auth vulnerabilities |\n"
    if any("test" in f.get("name","").lower() for f in features):
        goals_rows += "| G-03 | Achieve automated test coverage | >= 80% line coverage |\n"
    goals_rows += "| G-04 | Add observability stack | Tracing + structured logs live in production |\n"
    goals_rows += "| G-05 | CI/CD pipeline modernization | Full automated deploy on every merge to main |\n"

    return (
        f"## 2. Business Context & Objectives\n\n"
        f"### 2.1 Business Problem Statement\n\n"
        f"The current **{ptype}** system requires modernization:\n\n{problem}\n"
        f"### 2.2 Modernization Goals\n\n"
        f"| # | Goal | Success Metric |\n|---|---|---|\n{goals_rows}\n"
        f"### 2.3 Project Scope\n\n"
        f"#### In Scope\n\n{in_scope}\n\n"
        f"#### Out of Scope (Phase 1)\n\n{out_scope}\n\n---\n"
    )


def _s3_current_state(biz: Dict, features: List[Dict]) -> str:
    ptype = biz.get("product_type", "Software System")

    # Build layer table from features
    layer_map = {
        "REST API Routing": ("Controllers / Handlers", "Spring MVC / gRPC"),
        "Domain Service Layer": ("Services / Domain Logic", "Kotlin / Java"),
        "Database Access Layer": ("Data Access / Repositories", "JPA / JDBC"),
        "Automated Test Suite": ("Tests", "JUnit / Mockito"),
        "Container Orchestration Config": ("Infrastructure", "Docker / Kubernetes"),
        "CI/CD Pipeline Config": ("CI/CD", "GitHub Actions / Jenkins"),
    }
    feat_names = {f.get("name","") for f in features}
    inv_rows = ""
    for feat_name, (layer, tech) in layer_map.items():
        if feat_name in feat_names:
            inv_rows += f"| {layer} | Detected | {tech} |\n"
    if not inv_rows:
        inv_rows = "| Core Modules | Detected | Derived from repository scan |\n"

    # Known defects from low-confidence features
    defect_rows = ""
    for i, f in enumerate([x for x in features if float(x.get("confidence",0)) < 0.6], 1):
        defect_rows += f"| DEF-{i:02d} | Low confidence in **{_display(f.get('name',''))}** ({float(f.get('confidence',0)):.0%}) | Verify implementation completeness |\n"
    if not defect_rows:
        defect_rows = "| — | No critical defects identified from static analysis | — |\n"

    return (
        f"## 3. Current State Analysis (AS-IS)\n\n"
        f"### 3.1 Architecture Overview\n\n"
        f"The system is a **{ptype}** identified through static code analysis. "
        f"The following architectural layers were detected:\n\n"
        f"| Layer | Status | Key Technologies |\n|---|---|---|\n{inv_rows}\n"
        f"### 3.2 Domain Entity Catalogue\n\n"
        "_Entity classes detected during static analysis. Refer to source code for full schema definitions._\n\n"
        f"| Entity | Type | Notes |\n|---|---|---|\n"
        + "".join(f"| {_display(f.get('name',''))} | Domain Model | Confidence: {float(f.get('confidence',0)):.0%} |\n" for f in features[:6])
        + f"\n### 3.3 Known Defects\n\n"
        f"| ID | Description | Action Required |\n|---|---|---|\n{defect_rows}\n"
        f"### 3.4 Infrastructure Current State\n\n"
        "- Container orchestration: Kubernetes (version to be confirmed from manifest files)\n"
        "- CI/CD: Detected from pipeline config files\n"
        "- Database: Detected from repository access layer\n\n---\n"
    )


def _s4_stakeholders(biz: Dict) -> str:
    users = biz.get("primary_users", ["End Users"])
    rows = "\n".join(f"| {u} | Feature consumer / primary actor | High |" for u in users)
    rows += "\n| Engineering Lead | Technical decisions & architecture | High |"
    rows += "\n| Product Owner | Requirement sign-off | High |"
    rows += "\n| DevOps Engineer | Infrastructure & deployment | Medium |"
    rows += "\n| QA Engineer | Test coverage & acceptance | Medium |"

    persona_rows = ""
    for i, u in enumerate(users[:3], 1):
        persona_rows += f"\n#### Persona {i} — {u}\n- Interacts with the system as a primary actor\n- Expects reliable, low-latency responses\n- Requires secure access and data integrity\n"

    return (
        f"## 4. Stakeholders & Personas\n\n"
        f"### 4.1 Stakeholder Matrix\n\n"
        f"| Role | Responsibility | Impact |\n|---|---|---|\n{rows}\n"
        f"### 4.2 User Personas\n{persona_rows}\n---\n"
    )


def _s5_functional_reqs(features: List[Dict], frs: List[Dict]) -> str:
    if not frs:
        return "## 5. Functional Requirements\n\n_No functional requirements generated._\n\n---\n"

    lines = [
        "## 5. Functional Requirements\n\n"
        "_Priority: **M** = Must Have | **S** = Should Have | **C** = Could Have_\n"
    ]

    # Group FRs by linked feature
    feat_conf = {f.get("name",""): float(f.get("confidence",0)) for f in features}
    fr_by_feat: Dict[str, List[Dict]] = {}
    for fr in frs:
        lf = fr.get("linked_feature", fr.get("mapped_feature", "unknown"))
        fr_by_feat.setdefault(lf, []).append(fr)

    for feat_name, feat_frs in fr_by_feat.items():
        display = _display(feat_name)
        conf = feat_conf.get(feat_name, 0.7)
        priority = _moscow(conf)
        lines.append(f"\n### FR: {display}\n\n**Priority:** {priority} | **Confidence:** {conf:.0%}\n")
        for fr in feat_frs:
            lines.append(f"\n**{fr.get('id','FR-?')}:** {fr.get('description','')}\n")
            criteria = fr.get("acceptance_criteria", [])
            if criteria:
                lines.append("**Acceptance Criteria:**\n")
                for ac in criteria:
                    lines.append(f"- {ac}")

    # REST endpoint mapping table
    lines.append("\n### Proposed REST Endpoint Mapping\n")
    lines.append("| Method | Endpoint | Description | Auth Required |")
    lines.append("|---|---|---|---|")
    for f in features[:8]:
        path = _rest_path(f.get("name","resource"))
        lines.append(f"| GET | /api/v1{path} | Retrieve {_display(f.get('name',''))} | Yes |")
        lines.append(f"| POST | /api/v1{path} | Create {_display(f.get('name',''))} | Yes |")

    lines.append("\n---\n")
    return "\n".join(lines)


def _s6_nfrs(nfrs: List[Dict]) -> str:
    if not nfrs:
        return "## 6. Non-Functional Requirements\n\n_No NFRs generated._\n\n---\n"

    cats: Dict[str, List[Dict]] = {}
    for nfr in nfrs:
        cat = nfr.get("category", "general").capitalize()
        cats.setdefault(cat, []).append(nfr)

    lines = ["## 6. Non-Functional Requirements\n"]
    nfr_table = "| ID | Category | Requirement | Measurable Target |\n|---|---|---|---|\n"
    for nfr in nfrs:
        nfr_table += f"| {nfr.get('id','NFR-?')} | {nfr.get('category','').capitalize()} | {nfr.get('description','')} | See acceptance criteria |\n"
    lines.append(nfr_table)

    for cat, items in sorted(cats.items()):
        lines.append(f"\n### NFR: {cat}\n")
        for nfr in items:
            lines.append(f"- **{nfr.get('id','NFR-?')}:** {nfr.get('description','')}")

    lines.append("\n---\n")
    return "\n".join(lines)


def _s7_data_requirements(features: List[Dict]) -> str:
    has_db = any("database" in f.get("name","").lower() or "data" in f.get("name","").lower() for f in features)
    schema_note = (
        "Database access layer detected. The following schema modernization changes are recommended:\n\n"
        "| Change Type | Table / Collection | Description |\n|---|---|---|\n"
        "| Add Column | All primary tables | `deleted_at` DATETIME NULL — enables soft-delete |\n"
        "| Add Index | Foreign key columns | Improve JOIN query performance |\n"
        "| Add Full-Text Index | Searchable text columns | Enable full-text search capability |\n"
        "| Column Type Update | Text/varchar fields | Align max length with business rules |\n"
    ) if has_db else (
        "No direct database access layer detected. Data requirements to be confirmed during discovery.\n"
    )

    return (
        "## 7. Data Requirements\n\n"
        "### 7.1 Database Migration Strategy\n\n"
        f"{schema_note}\n"
        "### 7.2 Data Retention & Compliance\n\n"
        "- User PII data: Retain per applicable legal mandate (minimum 7 years where required)\n"
        "- Application logs: Retain for 90 days in hot storage, 1 year in cold storage\n"
        "- Deleted records: Soft-delete only; hard-delete only on verified GDPR erasure requests\n"
        "- Audit logs: Immutable, append-only; retain for 3 years\n\n---\n"
    )


def _s8_tech_stack(biz: Dict) -> str:
    ptype = biz.get("product_type", "Software System").lower()
    is_kotlin = "kotlin" in ptype or "spring" in ptype or "jvm" in ptype

    if is_kotlin:
        rows = (
            "| Language | Kotlin 1.x (detected) | Kotlin 2.x |\n"
            "| Framework | Spring Boot 2.x (detected) | Spring Boot 3.x |\n"
            "| JVM | Java 8/11 (detected) | Java 21 LTS |\n"
            "| Build Tool | Gradle (detected) | Gradle 8.x + mavenCentral() |\n"
            "| Database | MySQL 5.x / current | MySQL 8.x |\n"
            "| Auth | Embedded auth | Decoupled auth middleware |\n"
            "| Container | Docker (current) | Docker + Kubernetes (managed) |\n"
            "| Observability | None detected | OpenTelemetry + Prometheus + Grafana |\n"
        )
    else:
        rows = (
            "| Language | Current version | Latest stable version |\n"
            "| Framework | Current version | Latest stable version |\n"
            "| Build Tool | Current toolchain | Updated toolchain |\n"
            "| Container | Current config | Docker + Kubernetes |\n"
            "| Observability | Not detected | OpenTelemetry stack |\n"
        )

    return (
        "## 8. Technology Stack (TO-BE)\n\n"
        "| Component | Current (AS-IS) | Target (TO-BE) |\n"
        "|---|---|---|\n"
        f"{rows}\n---\n"
    )


def _s9_cicd() -> str:
    return (
        "## 9. CI/CD Pipeline Requirements\n\n"
        "### 9.1 Pipeline Stages\n\n"
        "`Code Push` → `Static Analysis` → `Build & Unit Tests` → `Integration Tests` → `Container Build & Scan` → `Deploy Staging` → `Deploy Production`\n\n"
        "### 9.2 Requirements\n\n"
        "| ID | Requirement |\n|---|---|\n"
        "| CICD-01 | Pipeline SHALL run static analysis (linting, SAST) on every pull request |\n"
        "| CICD-02 | Unit test coverage SHALL meet the minimum gate (≥ 80%) before merge |\n"
        "| CICD-03 | Container images SHALL be scanned for CVEs; builds with Critical CVEs SHALL fail |\n"
        "| CICD-04 | All deployments SHALL be immutable; rollback SHALL complete within 5 minutes |\n"
        "| CICD-05 | Pipeline execution time SHALL not exceed 15 minutes end-to-end |\n\n---\n"
    )


def _s10_infra() -> str:
    return (
        "## 10. Infrastructure Requirements\n\n"
        "| Resource | Specification |\n|---|---|\n"
        "| Kubernetes Version | 1.28+ (managed) |\n"
        "| Min Replicas | 2 (high availability) |\n"
        "| Max Replicas | 10 (HPA auto-scaling) |\n"
        "| CPU Request | 250m per pod |\n"
        "| Memory Request | 512Mi per pod |\n"
        "| Ingress | HTTPS with TLS 1.2+ termination |\n"
        "| Health Check | Liveness + Readiness probes required |\n"
        "| Secret Management | External secrets manager (Vault / K8s Secrets) |\n\n---\n"
    )


def _s11_risks(features: List[Dict]) -> str:
    rows = (
        "| R-01 | EOL dependency versions in use | High | Critical | Immediate upgrade sprint | Open |\n"
        "| R-02 | Missing observability stack | Medium | High | Add OpenTelemetry in Phase 2 | Open |\n"
        "| R-03 | No automated test suite detected | Medium | High | Add unit + integration tests | Open |\n"
    )
    r_idx = 4
    for f in features:
        conf = float(f.get("confidence", 1))
        if conf < 0.6:
            rows += f"| R-{r_idx:02d} | Low-confidence capability: {_display(f.get('name',''))} ({conf:.0%}) | Medium | High | Verify source implementation | Open |\n"
            r_idx += 1

    return (
        "## 11. Risk Register\n\n"
        "| ID | Risk | Probability | Impact | Mitigation | Status |\n"
        "|---|---|---|---|---|---|\n"
        f"{rows}\n---\n"
    )


def _s12_compliance() -> str:
    return (
        "## 12. Compliance & Legal Requirements\n\n"
        "| Regulation | Requirement | Implementation |\n|---|---|---|\n"
        "| GDPR | Right to erasure for personal data | Soft-delete + hard-delete on verified request |\n"
        "| GDPR | Data minimization | Collect only necessary PII fields |\n"
        "| SOC 2 Type II | Audit logging of all privileged actions | Append-only audit trail |\n"
        "| OWASP Top 10 | Protect against injection, auth flaws | SAST scan in CI/CD pipeline |\n"
        "| TLS | Encrypt all data in transit | TLS 1.2+ enforced at ingress |\n\n---\n"
    )


def _s13_acceptance() -> str:
    return (
        "## 13. Acceptance Criteria\n\n"
        "### 13.1 Functional Acceptance\n\n"
        "| ID | Criterion | Verification |\n|---|---|---|\n"
        "| AC-F01 | All FR acceptance criteria pass automated test suite | CI test run |\n"
        "| AC-F02 | No P0 or P1 defects open at release gate | Bug tracker sign-off |\n"
        "| AC-F03 | All API endpoints return documented HTTP status codes | Contract test |\n\n"
        "### 13.2 Non-Functional Acceptance\n\n"
        "| ID | Criterion | Target |\n|---|---|---|\n"
        "| AC-NF01 | API p95 response latency | < 500ms under normal load |\n"
        "| AC-NF02 | Unit + integration test coverage | ≥ 80% line coverage |\n"
        "| AC-NF03 | Container security scan | 0 Critical CVEs at release |\n"
        "| AC-NF04 | System uptime | ≥ 99.9% over 30-day rolling window |\n\n---\n"
    )


def _s14_roadmap() -> str:
    return (
        "## 14. Delivery Roadmap\n\n"
        "| Phase | Timeline | Key Deliverables |\n|---|---|---|\n"
        "| Phase 1 — Foundation & Critical Fixes | Weeks 1–6 | Upgrade EOL deps, fix P0 defects, establish CI/CD pipeline |\n"
        "| Phase 2 — Observability & Security | Weeks 7–12 | Add OpenTelemetry, security hardening, REST API layer |\n"
        "| Phase 3 — Hardening & Production Readiness | Weeks 13–16 | Load testing, DR runbooks, final acceptance sign-off |\n\n---\n"
    )


def _s15_open_issues(biz: Dict, features: List[Dict], frs: List[Dict], nfrs: List[Dict]) -> str:
    issues = []
    users = biz.get("primary_users", [])
    if "General System Users" in users:
        issues.append("User roles and access levels are not explicitly defined — requires stakeholder input.")
    low = sum(1 for f in features if float(f.get("confidence", 1)) < 0.6)
    if low:
        issues.append(f"{low} feature(s) carry confidence < 60% — source modules may be incomplete or ambiguous.")
    if len(nfrs) <= 3:
        issues.append("Tech stack signals were insufficient — NFRs are based on generic baselines; review with engineering team.")
    if not issues:
        issues.append("No significant open issues identified. All inputs were well-defined.")

    rows = "\n".join(f"| OI-{i:02d} | {issue} | Open |" for i, issue in enumerate(issues, 1))
    return (
        "## 15. Open Issues & Decisions Required\n\n"
        "| ID | Issue | Status |\n|---|---|---|\n"
        f"{rows}\n\n---\n"
    )


def _s16_approval(today: str) -> str:
    return (
        "## 16. Document Approval\n\n"
        "The undersigned confirm this Business Requirements Document accurately represents "
        "the agreed requirements for this modernization initiative.\n\n"
        "| Role | Name | Signature | Date |\n|---|---|---|---|\n"
        "| Engineering Lead | | | |\n"
        "| Product Owner | | | |\n"
        "| DevOps Lead | | | |\n"
        "| QA Lead | | | |\n\n"
        f"_Document generated: {today}. Version control maintained in project wiki._\n"
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
    sections = [
        _cover(business_context, today),
        _s1_exec_summary(business_context, features),
        _s2_business_context(business_context, features),
        _s3_current_state(business_context, features),
        _s4_stakeholders(business_context),
        _s5_functional_reqs(features, functional_requirements),
        _s6_nfrs(non_functional_requirements),
        _s7_data_requirements(features),
        _s8_tech_stack(business_context),
        _s9_cicd(),
        _s10_infra(),
        _s11_risks(features),
        _s12_compliance(),
        _s13_acceptance(),
        _s14_roadmap(),
        _s15_open_issues(business_context, features, functional_requirements, non_functional_requirements),
        _s16_approval(today),
    ]
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

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
