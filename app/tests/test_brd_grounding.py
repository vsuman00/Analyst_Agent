"""
test_brd_grounding.py — Regression suite for BRD accuracy / evidence-groundedness
------------------------------------------------------------------------------------
Runs deterministic checks against:
  1. Evidence manifest unit tests (using cloned repo fixture dirs)
  2. BRD file content assertions (6 test repos)
  3. FR batching mock test
  4. Validator 9th dimension (tech grounding)

Run with:
  pytest app/tests/test_brd_grounding.py -v
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict
from unittest.mock import patch, MagicMock

import pytest

# ─── helpers ────────────────────────────────────────────────────────────────
REPO_DIR = Path(__file__).parent.parent.parent / "runtime" / "runner_cache"
BRD_DIR  = Path(__file__).parent.parent.parent / "runtime" / "pipeline_out"


def _empty_api_data() -> Dict:
    return {"endpoints": [], "grpc_rpcs": []}


def _empty_dep_data(language: str = "unknown", build_tool: str = "unknown") -> Dict:
    return {"dependencies": [], "language": language, "build_tool": build_tool}


def _load_brd(repo_stem: str) -> str:
    """Load a generated BRD markdown file if it exists."""
    candidates = list(BRD_DIR.glob(f"BRD_{repo_stem}*.md"))
    if not candidates:
        pytest.skip(f"No BRD file found for {repo_stem!r} in {BRD_DIR}")
    return candidates[0].read_text(encoding="utf-8")


# ─── 1. Evidence Manifest Unit Tests ────────────────────────────────────────

class TestEvidenceManifest:
    """Unit tests for build_evidence_manifest using a temp directory."""

    @pytest.fixture()
    def tmp_repo(self, tmp_path):
        """Create a minimal fake repo directory."""
        return tmp_path

    def test_empty_repo_defaults(self, tmp_repo):
        from app.eca.evidence_manifest import build_evidence_manifest
        m = build_evidence_manifest(tmp_repo, _empty_api_data(), _empty_dep_data())
        assert m["has_http_api"] is False
        assert m["has_android"] is False
        assert m["has_kubernetes"] is False
        assert m["has_docker"] is False
        assert m["has_gdpr_mention"] is False
        assert m["platform"] == "library"  # no signals → library/unknown

    def test_android_detection(self, tmp_repo):
        from app.eca.evidence_manifest import build_evidence_manifest
        (tmp_repo / "app" / "src" / "main").mkdir(parents=True)
        (tmp_repo / "app" / "src" / "main" / "AndroidManifest.xml").write_text(
            '<manifest package="com.example.app"/>', encoding="utf-8"
        )
        m = build_evidence_manifest(tmp_repo, _empty_api_data(), _empty_dep_data("kotlin", "gradle"))
        assert m["has_android"] is True
        assert m["platform"] == "android"

    def test_docker_detection(self, tmp_repo):
        from app.eca.evidence_manifest import build_evidence_manifest
        (tmp_repo / "Dockerfile").write_text("FROM openjdk:17\n", encoding="utf-8")
        m = build_evidence_manifest(tmp_repo, _empty_api_data(), _empty_dep_data("java", "gradle"))
        assert m["has_docker"] is True
        assert m["has_kubernetes"] is False

    def test_kubernetes_manifest_detection(self, tmp_repo):
        from app.eca.evidence_manifest import build_evidence_manifest
        (tmp_repo / "k8s").mkdir()
        (tmp_repo / "k8s" / "deployment.yaml").write_text(
            "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: app\n",
            encoding="utf-8",
        )
        m = build_evidence_manifest(tmp_repo, _empty_api_data(), _empty_dep_data())
        assert m["has_kubernetes"] is True

    def test_http_api_from_extractor(self, tmp_repo):
        from app.eca.evidence_manifest import build_evidence_manifest
        api_data = {
            "endpoints": [
                {"method": "GET", "path": "/api/pets", "handler": "listPets", "source_file": "PetController.java"},
                {"method": "POST", "path": "/api/pets", "handler": "createPet", "source_file": "PetController.java"},
            ],
            "grpc_rpcs": [],
        }
        m = build_evidence_manifest(tmp_repo, api_data, _empty_dep_data("java", "maven"))
        assert m["has_http_api"] is True
        assert len(m["actual_endpoints"]) == 2

    def test_gdpr_detection_in_readme(self, tmp_repo):
        from app.eca.evidence_manifest import build_evidence_manifest
        (tmp_repo / "README.md").write_text(
            "This application processes personal data and is GDPR-compliant.\n",
            encoding="utf-8",
        )
        m = build_evidence_manifest(tmp_repo, _empty_api_data(), _empty_dep_data())
        assert m["has_gdpr_mention"] is True

    def test_no_gdpr_without_mention(self, tmp_repo):
        from app.eca.evidence_manifest import build_evidence_manifest
        (tmp_repo / "README.md").write_text(
            "A simple weather application showing current temperature.\n",
            encoding="utf-8",
        )
        m = build_evidence_manifest(tmp_repo, _empty_api_data(), _empty_dep_data())
        assert m["has_gdpr_mention"] is False

    def test_auth_detection_from_dep(self, tmp_repo):
        from app.eca.evidence_manifest import build_evidence_manifest
        dep_data = {
            "dependencies": [{"name": "spring-security-core", "category": "framework"}],
            "language": "java", "build_tool": "gradle",
        }
        m = build_evidence_manifest(tmp_repo, _empty_api_data(), dep_data)
        assert m["has_auth"] is True

    def test_database_detection_from_dep(self, tmp_repo):
        from app.eca.evidence_manifest import build_evidence_manifest
        dep_data = {
            "dependencies": [
                {"name": "spring-boot-starter-data-jpa", "category": "framework"},
                {"name": "mysql-connector-java", "category": "database"},
            ],
            "language": "java", "build_tool": "gradle",
        }
        m = build_evidence_manifest(tmp_repo, _empty_api_data(), dep_data)
        assert m["has_database"] is True
        assert "mysql-connector-java" in m["dep_categories"]["database"]


# ─── 2. BRD File Content Assertions (6 golden repos) ────────────────────────

class TestBRDContentAssertions:
    """
    Golden assertions against previously-generated BRD files.
    Tests fail if BRD files don't exist (skip) or if known hallucination
    patterns are detected.
    """

    def test_android_brd_no_kubernetes_hallucination(self):
        """Android repo BRDs must NOT claim Kubernetes infrastructure."""
        brd = _load_brd("android-kotlin-golang-example-project")
        # If K8s is mentioned, it should be flagged as "not evidenced"
        # rather than stated as a delivery requirement
        if "Kubernetes" in brd or "k8s" in brd:
            # Acceptable only if the BRD explicitly says "not evidenced"
            assert "not evidenced" in brd.lower() or "No server infrastructure" in brd, (
                "Android BRD claims Kubernetes without evidence — hallucination detected"
            )

    def test_android_brd_has_mobile_platform(self):
        """Android repo BRDs should identify the platform as mobile/Android."""
        brd = _load_brd("android-kotlin-golang-example-project")
        assert (
            "android" in brd.lower() or
            "mobile" in brd.lower() or
            "app store" in brd.lower() or
            "google play" in brd.lower()
        ), "Android BRD does not mention Android/mobile platform"

    def test_weather_brd_no_gdpr_hallucination(self):
        """
        Weather app BRD must NOT write a GDPR compliance block unless the README
        mentions GDPR (it doesn't for a simple weather app).
        """
        brd = _load_brd("Weather_App")
        if "GDPR" in brd:
            # Acceptable if explicitly flagged as not evidenced
            assert "not evidenced" in brd.lower(), (
                "Weather App BRD claims GDPR compliance without evidence — hallucination"
            )

    def test_petclinic_has_rest_api_evidence(self):
        """Spring PetClinic is a web app — its BRD should mention REST API."""
        brd = _load_brd("spring-petclinic-kotlin")
        # PetClinic definitely has HTTP endpoints — they should appear
        assert (
            "REST" in brd or "endpoint" in brd.lower() or "http" in brd.lower()
        ), "PetClinic BRD missing REST API evidence"

    def test_petclinic_has_database_section(self):
        """Spring PetClinic uses JPA/HSQL — the data requirements section should reflect this."""
        brd = _load_brd("spring-petclinic-kotlin")
        assert "## 7. Data Requirements" in brd, "Data Requirements section missing"
        # Should NOT say 'no persistence layer detected'
        assert "no persistence layer detected" not in brd.lower(), (
            "PetClinic BRD incorrectly reports no persistence layer — JPA/HSQL not detected"
        )

    def test_od_system_no_phantom_compliance(self):
        """OD System Analyser BRD should not fabricate GDPR compliance if not in README."""
        brd = _load_brd("OD_System_Analyser")
        if "GDPR" in brd:
            assert "not evidenced" in brd.lower(), (
                "OD System BRD fabricates GDPR compliance — hallucination"
            )

    def test_twitter_clone_has_auth_mention(self):
        """Twitter clone has auth — BRD should acknowledge it in compliance or data section."""
        brd = _load_brd("twitter-clone-app-kotlin")
        assert (
            "auth" in brd.lower() or
            "authentication" in brd.lower() or
            "jwt" in brd.lower() or
            "security" in brd.lower()
        ), "Twitter clone BRD missing authentication evidence"


# ─── 3. FR Batching Unit Test ────────────────────────────────────────────────

class TestFRBatching:
    """Verify that enrich_functional_requirements processes FRs in batches."""

    def test_batching_splits_correctly(self):
        from app.analysis.brd_enrichment_agent import enrich_functional_requirements

        # Generate 20 fake FRs
        frs = [
            {"id": f"FR-{i}", "linked_feature": f"feature_{i}", "description": f"The system SHALL do thing {i}.", "acceptance_criteria": []}
            for i in range(1, 21)
        ]
        features = [{"name": f"feature_{i}", "description": f"Feature {i}", "source_modules": []} for i in range(1, 21)]

        call_count = 0

        def mock_safe_call(system, user, max_tokens, tag):
            nonlocal call_count
            call_count += 1
            # Return a fake enriched FR for each ID in the batch
            # Parse how many FRs are in the batch from the user prompt
            batch_ids = [f"FR-{i}" for i in range(1, 21) if f'"FR-{i}"' in user]
            return {
                "enriched_frs": [{"id": fr_id, "plain_english": "test", "technical_note": "test", "business_impact": "test", "acceptance_criteria": []} for fr_id in batch_ids],
                "glossary_terms": [],
            }

        with patch("app.analysis.brd_enrichment_agent._safe_call", side_effect=mock_safe_call):
            result = enrich_functional_requirements(frs, features, batch_size=8)

        # 20 FRs / 8 per batch → should be 3 calls (8 + 8 + 4)
        assert call_count == 3, f"Expected 3 batch calls, got {call_count}"
        assert "enriched_frs" in result

    def test_batching_empty_frs(self):
        from app.analysis.brd_enrichment_agent import enrich_functional_requirements
        result = enrich_functional_requirements([], [])
        assert result == {}


# ─── 4. Validator 9th Dimension ──────────────────────────────────────────────

class TestTechGrounding:
    """Unit tests for the _score_tech_grounding dimension."""

    def _get_scorer(self):
        from app.analysis.brd_validator import _score_tech_grounding
        return _score_tech_grounding

    def test_no_evidence_passes(self):
        score, issues = self._get_scorer()("Some BRD mentioning Kubernetes", {})
        assert score == 1.0
        assert issues == []

    def test_grounded_kubernetes(self):
        """Kubernetes in BRD + evidence says has_kubernetes=True → passes."""
        score, issues = self._get_scorer()(
            "The system uses a Kubernetes Cluster for deployment.",
            {"has_kubernetes": True}
        )
        assert score == 1.0
        assert issues == []

    def test_phantom_kubernetes(self):
        """Kubernetes in BRD but evidence says has_kubernetes=False → fails."""
        score, issues = self._get_scorer()(
            "The system uses Kubernetes for container orchestration.",
            {"has_kubernetes": False}
        )
        assert score < 1.0
        assert any("Kubernetes" in i for i in issues)

    def test_phantom_gdpr(self):
        """GDPR in BRD but evidence says has_gdpr_mention=False → fails."""
        score, issues = self._get_scorer()(
            "The system must comply with GDPR regulations for data protection.",
            {"has_gdpr_mention": False}
        )
        assert score < 1.0
        assert any("GDPR" in i for i in issues)

    def test_grounded_android(self):
        """Android in BRD + evidence has_android=True → passes."""
        score, issues = self._get_scorer()(
            "The application is deployed to the Android platform via Google Play.",
            {"has_android": True, "has_http_api": False}
        )
        assert score == 1.0
        assert issues == []

    def test_phantom_rest_api(self):
        """REST API in BRD but evidence says has_http_api=False → fails."""
        score, issues = self._get_scorer()(
            "The system exposes a RESTful API with standard HTTP endpoints.",
            {"has_http_api": False}
        )
        assert score < 1.0
        assert any("REST" in i or "RESTful" in i for i in issues)

    def test_no_tech_claims_passes(self):
        """A BRD with no technology terms always passes grounding check."""
        brd = "This is a business requirements document with general requirements."
        score, issues = self._get_scorer()(brd, {"has_kubernetes": False, "has_android": False})
        assert score == 1.0
        assert issues == []


# ─── 5. Validate BRD Integration ─────────────────────────────────────────────

class TestValidateBRDWithEvidence:
    """Integration test: validate_brd should respect evidence in 9th dimension."""

    def _minimal_brd_with_kubernetes(self) -> str:
        """A minimal BRD claiming Kubernetes for testing grounding."""
        sections = [
            "## 1. Executive Summary\n\nThis BRD describes a system. " + "word " * 30,
            "## 2. Business Context & Objectives\n\n" + "word " * 30,
            "## 3. Current State Analysis\n\n" + "word " * 30,
            "## 4. Stakeholders & Personas\n\n" + "word " * 30,
            "## 5. Functional Requirements\n\nThe system SHALL process data. FR-1 SHALL validate input.\n" + "word " * 30,
            "## 6. Non-Functional Requirements\n\nNFR-1 SHALL achieve 99.9% uptime\n" + "word " * 30,
            "## 7. Data Requirements\n\n" + "word " * 30,
            "## 8. Technology Stack\n\n" + "word " * 30,
            "## 9. CI/CD Pipeline\n\nKubernetes deployment pipeline. " + "word " * 30,
            "## 10. Infrastructure Requirements\n\nKubernetes Cluster deployment. " + "word " * 30,
            "## 11. Risk Register\n\n" + "word " * 30,
            "## 12. Compliance & Legal\n\n" + "word " * 30,
            "## 13. Acceptance Criteria\n\n" + "word " * 30,
            "## 14. Delivery Roadmap\n\n" + "word " * 30,
            "## 15. Open Issues & Decisions\n\n" + "word " * 30,
            "## 16. Document Approval\n\n" + "word " * 30,
        ]
        return "\n\n".join(sections)

    def test_kubernetes_hallucination_lowers_score(self):
        from app.analysis.brd_validator import validate_brd
        brd = self._minimal_brd_with_kubernetes()
        features = [{"name": "data_processing", "description": "Processes data.", "confidence": 0.9, "merge_of": []}]
        frs = [{"id": "FR-1", "description": "The system SHALL validate input.", "linked_feature": "data_processing"}]

        result_no_evidence = validate_brd(brd, features, frs, evidence={})
        result_with_evidence = validate_brd(brd, features, frs, evidence={"has_kubernetes": False})

        # With evidence that K8s is absent, score should be lower
        assert result_with_evidence.score < result_no_evidence.score
        grounding_issues = [i for i in result_with_evidence.issues if "[GROUNDING]" in i]
        assert len(grounding_issues) > 0
