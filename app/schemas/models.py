from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal

class FileChunk(BaseModel):
    file: str
    content: str

class ClassifiedFiles(BaseModel):
    frontend: List[str] = Field(default_factory=list)
    backend: List[str] = Field(default_factory=list)
    config: List[str] = Field(default_factory=list)
    docs: List[str] = Field(default_factory=list)
    unknown: List[str] = Field(default_factory=list)

class ECAOutput(BaseModel):
    readme: str = ""
    file_tree: Dict[str, Any] = Field(default_factory=dict)
    classified_files: ClassifiedFiles = Field(default_factory=ClassifiedFiles)
    chunks: List[FileChunk] = Field(default_factory=list)

class Feature(BaseModel):
    name: str
    confidence: float
    sources: List[str] = Field(default_factory=list)

class NormalizedContext(BaseModel):
    features: List[Feature] = Field(default_factory=list)
    modules: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# PayloadConverter output schemas
# ---------------------------------------------------------------------------

class AnalysisFeature(BaseModel):
    """A product-level feature derived deterministically from the final payload."""
    id: str                          # feat-XXX, derived from index
    name: str                        # Human-readable feature name
    confidence: float                # 0.0–1.0, propagated from builder.py logic
    sources: List[str]               # Source file paths that triggered detection
    category: str                    # One of: core_pipeline, api, feature_detection, unknown


class Requirement(BaseModel):
    """A functional requirement derived from a detected feature or validation output."""
    id: str                          # REQ-XXX
    feature_id: str                  # Parent AnalysisFeature.id
    description: str                 # SHALL-style statement
    priority: Literal["High", "Medium", "Low"]
    source_modules: List[str]        # Module names that evidence this requirement


class MinimalBRD(BaseModel):
    """Minimal, structured BRD derived purely from the pipeline's final payload."""
    repo_name: str
    summary: str                     # One-line system summary, derived from module set
    validation_score: float
    validation_passed: bool
    features: List[AnalysisFeature]
    requirements: List[Requirement]
    gaps: List[str]                  # Propagated from ContextBuilder gap analysis
    modules_detected: List[str]      # Normalized module names from final payload


# ---------------------------------------------------------------------------
# FeatureExtractionAgent output schemas
# ---------------------------------------------------------------------------

class ExtractedFeature(BaseModel):
    """
    A real, module-backed feature produced by FeatureExtractionAgent.

    Rules:
      - id       : feat-NNN (zero-padded, 1-indexed, stable within a run)
      - name     : Short technical label derived from keyword cluster + module name
      - description : Concise technical description (≤ 2 sentences), no business fluff
      - source_modules : ≥ 1 normalized module name; features with 0 modules are rejected
      - confidence : 0.5–0.7 if inferred from content only; 0.8–1.0 if keyword+module both match
    """
    id: str
    name: str
    description: str
    source_modules: List[str]
    confidence: float


class FeatureExtractionResult(BaseModel):
    """Top-level output envelope for FeatureExtractionAgent."""
    features: List[ExtractedFeature]


# ---------------------------------------------------------------------------
# FeatureValidator output schemas
# ---------------------------------------------------------------------------

class ValidatedFeature(BaseModel):
    """
    A deduplicated, merged, and normalized feature produced by FeatureValidator.

    Rules:
      - id          : feat-NNN (re-indexed after dedup/merge, 1-based, zero-padded)
      - name        : snake_case canonical identifier (e.g. token_based_authentication)
      - description : Kept from highest-confidence input; NOT rewritten
      - confidence  : max-pooled from all merged inputs; never inflated
      - merge_of    : original input ids that were collapsed into this entry (audit trail)
    """
    id: str
    name: str
    description: str
    confidence: float
    merge_of: List[str] = Field(default_factory=list)


class FeatureValidationResult(BaseModel):
    """Top-level output envelope for FeatureValidator."""
    validated_features: List[ValidatedFeature]


# ---------------------------------------------------------------------------
# FeatureInterpretationAgent output schemas
# ---------------------------------------------------------------------------

class InterpretedFeature(BaseModel):
    """
    A feature that has been interpreted from raw signals and mapped to evidence.
    """
    id: str
    name: str
    description: str
    evidence: List[str]
    confidence: float


class FeatureInterpretationResult(BaseModel):
    """Top-level output envelope for FeatureInterpretationAgent."""
    features: List[InterpretedFeature]


# ---------------------------------------------------------------------------
# BusinessUnderstandingAgent output schemas
# ---------------------------------------------------------------------------

class BusinessContext(BaseModel):
    """
    Business context derived deterministically from features and system type.
    """
    product_type: str
    primary_users: List[str]
    core_value: str


class BusinessUnderstandingResult(BaseModel):
    """Top-level output envelope for BusinessUnderstandingAgent."""
    business_context: BusinessContext


# ---------------------------------------------------------------------------
# ProductUnderstandingAgent output schemas
# ---------------------------------------------------------------------------

class ProductProfile(BaseModel):
    """
    Structured product understanding derived purely from validated features.

    Rules:
      - name             : snake_case label synthesised from dominant feature cluster;
                           never hallucinated or sourced externally
      - summary          : ≤ 120 words; template-driven from feature names; no fluff
      - core_capabilities: human-readable title-case strings, one per validated feature
                           with confidence ≥ CAPABILITY_THRESHOLD (0.7 default)
    """
    name: str
    summary: str
    core_capabilities: List[str]


class ProductUnderstandingResult(BaseModel):
    """Top-level output envelope for ProductUnderstandingAgent."""
    product: ProductProfile


# ---------------------------------------------------------------------------
# FunctionalRequirementGenerator output schemas
# ---------------------------------------------------------------------------

class FunctionalRequirement(BaseModel):
    """
    A single testable functional requirement derived from one validated feature.

    Rules:
      - id            : "FR-N" (1-indexed, no zero-padding per spec)
      - description   : SHALL-style, specific and testable; no vague qualifiers
      - linked_feature: snake_case name of the source ValidatedFeature or InterpretedFeature
      - acceptance_criteria: List of testable criteria
    """
    id: str
    description: str
    linked_feature: str
    acceptance_criteria: List[str]


class FunctionalRequirementsResult(BaseModel):
    """Top-level output envelope for FunctionalRequirementGenerator."""
    functional_requirements: List[FunctionalRequirement]


# ---------------------------------------------------------------------------
# NonFunctionalRequirementGenerator output schemas
# ---------------------------------------------------------------------------

class NonFunctionalRequirement(BaseModel):
    """
    A single non-functional requirement inferred from system context.

    Rules:
      - id          : "NFR-N" (1-indexed)
      - category    : one of "performance" | "security" | "scalability" | "availability"
      - description : SHALL-style; includes a measurable condition or boundary;
                      inferred only from tech_stack and system_type.
    """
    id: str
    category: Literal["performance", "security", "scalability", "availability"]
    description: str


class NonFunctionalRequirementsResult(BaseModel):
    """Top-level output envelope for NonFunctionalRequirementGenerator."""
    non_functional_requirements: List[NonFunctionalRequirement]


# ---------------------------------------------------------------------------
# BRDValidator output schemas
# ---------------------------------------------------------------------------

class BRDValidationResult(BaseModel):
    """
    Result of rule-based validation on a generated Markdown BRD.

    Rules:
      - score         : 0.0 to 1.0 (evaluating completeness, consistency, clarity)
      - issues        : List of specific violations found during parsing
      - needs_revision: True if score < 0.85
    """
    score: float
    issues: List[str]
    needs_revision: bool


# ---------------------------------------------------------------------------
# RepoEvidenceManifest — assembled by evidence_manifest.py
# ---------------------------------------------------------------------------

class DepCategories(BaseModel):
    """Dependency names grouped by role, derived from build file analysis."""
    database:  List[str] = Field(default_factory=list)
    auth:      List[str] = Field(default_factory=list)
    grpc:      List[str] = Field(default_factory=list)
    infra:     List[str] = Field(default_factory=list)
    framework: List[str] = Field(default_factory=list)
    other:     List[str] = Field(default_factory=list)


class RepoEvidence(BaseModel):
    """
    Structured evidence about what a repository ACTUALLY contains.

    Assembled by evidence_manifest.build_evidence_manifest() from:
      - api_extractor output    → HTTP endpoints and gRPC definitions
      - dependency_extractor    → declared libraries and their categories
      - file system scan        → Dockerfile, AndroidManifest.xml, k8s/ dir, etc.
      - README/docs text scan   → GDPR/PII/compliance keyword mentions

    Every downstream stage (BRD composer, archetype detector, validator)
    queries this model instead of maintaining hardcoded domain-keyword lists.
    """
    # API signals
    has_http_api:     bool = False
    has_grpc:         bool = False
    actual_endpoints: List[Dict[str, Any]] = Field(default_factory=list)
    grpc_rpcs:        List[Dict[str, Any]] = Field(default_factory=list)

    # Dependency signals
    has_database: bool = False
    has_auth:     bool = False
    detected_deps: List[Dict[str, Any]] = Field(default_factory=list)
    dep_categories: DepCategories = Field(default_factory=DepCategories)

    # Infrastructure signals (from actual files)
    has_docker:     bool = False
    has_kubernetes: bool = False
    infra_files:    List[str] = Field(default_factory=list)

    # Platform signals
    has_android: bool = False
    has_ios:     bool = False
    has_desktop: bool = False
    platform:    str  = "unknown"  # "android"|"ios"|"desktop"|"web"|"server"|"library"|"unknown"

    # Quality signals
    has_gdpr_mention: bool = False
    has_tests:        bool = False

    # Build metadata
    build_tool:       str = "unknown"
    primary_language: str = "unknown"
