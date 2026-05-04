from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import traceback
import os

app = FastAPI(
    title="Analyst Agent API",
    description="Enterprise-grade AI backend system for converting GitHub repositories into Business Requirement Documents (BRDs).",
    version="1.0.0",
)

# Mount the static directory to serve HTML
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalyzeRequest(BaseModel):
    repo_url: str
    output_path: Optional[str] = None


class ConvertRequest(BaseModel):
    """Accepts a pre-computed final pipeline payload and converts it to a MinimalBRD."""
    payload: Dict[str, Any]

@app.post("/analyze")
async def analyze_repo(request: AnalyzeRequest):
    from app.pipeline.runner import run_pipeline
    try:
        # Run the deterministic data pipeline synchronously
        final_payload = run_pipeline(repo_url=request.repo_url, output_path=request.output_path)
        return {"status": "success", "data": final_payload}
    except Exception as e:
        error_msg = str(e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {error_msg}")

@app.get("/")
async def root():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message": "Analyst Agent API is running. Visit /docs for the interactive API documentation."}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "Analyst Agent"}


@app.post("/convert")
async def convert_payload(request: ConvertRequest):
    """
    Convert a pre-computed final pipeline payload into Features, Requirements,
    and a minimal BRD.

    Input : { "payload": { ...final_payload... } }
    Output: { "status": "success", "brd": { ...MinimalBRD... } }
    """
    from app.analysis.payload_converter import build_brd
    try:
        brd = build_brd(request.payload)
        return {"status": "success", "brd": brd.model_dump()}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")


@app.post("/analyze-and-convert")
async def analyze_and_convert(request: AnalyzeRequest):
    """
    End-to-end: Full 10-stage pipeline execution.
    Returns:
      - pipeline: raw canonical payload
      - brd: structured MinimalBRD object
      - markdown: final formatted & fixed BRD markdown
    """
    from app.pipeline.runner import run_pipeline
    from app.analysis.payload_converter import build_brd
    from app.analysis.feature_extraction_agent import extract_features
    from app.analysis.feature_validator import validate_features
    from app.analysis.product_understanding_agent import understand_product
    from app.analysis.business_understanding_agent import understand_business
    from app.analysis.functional_requirement_generator import generate_requirements
    from app.analysis.non_functional_requirement_generator import generate_nfrs
    from app.analysis.brd_composer import compose_brd
    from app.analysis.brd_fix_loop import run_fix_loop
    import os

    try:
        # 1. Phase 1: Context Extraction
        final_payload = run_pipeline(
            repo_url=request.repo_url,
            output_path=request.output_path,
        )

        # 2. Extract components for full analysis
        # FIX (Bug 1.2): final_output_builder.py stores key as "modules" not "normalized_modules"
        norm_modules = final_payload.get("modules", final_payload.get("normalized_modules", []))
        chunks = final_payload.get("chunks", [])

        # 3. Phase 2: Analysis
        feat_ext = extract_features(norm_modules, chunks)
        val_feats = validate_features(feat_ext.model_dump()["features"])
        val_feats_list = val_feats.model_dump()["validated_features"]
        prod_und = understand_product(val_feats_list)
        prod_dict = prod_und.model_dump()

        # 4. Phase 3: Requirements
        fr_gen = generate_requirements(val_feats_list)
        tech_stack = final_payload.get("tech_stack", [])
        system_type = prod_dict["product"]["name"]
        nfr_gen = generate_nfrs(system_type=system_type, tech_stack=tech_stack)

        # 5. Optional LLM Enrichment
        from app.pipeline.runner import _try_enrich
        enriched_feats, prod_enriched = _try_enrich(val_feats_list, prod_dict)

        # FIX (Bug 1.3): Call BusinessUnderstandingAgent explicitly so compose_brd()
        # receives real product_type, primary_users, core_value — not fallback strings.
        biz_result = understand_business(
            enriched_feats,
            system_type=prod_dict["product"]["name"]
        )
        biz_ctx = biz_result.model_dump()["business_context"]
        # Augment with product-level summary fields
        biz_ctx["product_summary"] = prod_dict["product"].get("summary", "")
        biz_ctx["core_capabilities"] = prod_dict["product"].get("core_capabilities", [])
        biz_ctx["repo_name"] = final_payload.get("repo_name", request.repo_url.rstrip("/").rsplit("/", 1)[-1])

        feat_list = enriched_feats if isinstance(enriched_feats, list) else []
        fr_list = fr_gen.model_dump().get("functional_requirements", [])
        nfr_list = nfr_gen.model_dump().get("non_functional_requirements", [])

        # 6. Phase 4: Composition & Fix Loop
        initial_markdown = compose_brd(
            business_context=biz_ctx,
            features=feat_list,
            functional_requirements=fr_list,
            non_functional_requirements=nfr_list,
        )

        loop_result = run_fix_loop(
            initial_markdown,
            features=feat_list,
            functional_requirements=fr_list,
        )
        final_markdown = loop_result["final_markdown"]

        # 7. Build MinimalBRD for structural response
        brd_struct = build_brd(final_payload)

        return {
            "status": "success",
            "pipeline": final_payload,
            "brd": brd_struct.model_dump(),
            "markdown": final_markdown,
            "validation": loop_result["final_validation"]
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Full pipeline execution failed: {str(e)}")



class ExtractFeaturesRequest(BaseModel):
    """
    Input for FeatureExtractionAgent.

    normalized_modules : from ContextNormalizer output
        [{ "id": str, "name": str, "files": [str], "confidence": float }]
    chunks : from ContentProcessor output (content used as summarized context)
        [{ "chunk_id": str, "file_path": str, "category": str, "content": str }]
    """
    normalized_modules: List[Dict[str, Any]]
    chunks: List[Dict[str, Any]]


@app.post("/extract-features")
async def extract_features_endpoint(request: ExtractFeaturesRequest):
    """
    Run FeatureExtractionAgent on pre-computed normalized_modules + chunks.

    Input : { "normalized_modules": [...], "chunks": [...] }
    Output: { "status": "success", "data": { "features": [...] } }
    """
    from app.analysis.feature_extraction_agent import extract_features
    try:
        result = extract_features(request.normalized_modules, request.chunks)
        return {"status": "success", "data": result.model_dump()}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Feature extraction failed: {str(e)}")


class ValidateFeaturesRequest(BaseModel):
    """
    Input for FeatureValidator.

    features : output of FeatureExtractionAgent
        [{ "id": str, "name": str, "description": str,
           "source_modules": [str], "confidence": float }]
    """
    features: List[Dict[str, Any]]


@app.post("/validate-features")
async def validate_features_endpoint(request: ValidateFeaturesRequest):
    """
    Run FeatureValidator: deduplicate, merge overlapping features,
    and normalise names to snake_case.

    Input : { "features": [ ...ExtractedFeature list... ] }
    Output: { "status": "success", "data": { "validated_features": [...] } }
    """
    from app.analysis.feature_validator import validate_features
    try:
        result = validate_features(request.features)
        return {"status": "success", "data": result.model_dump()}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Feature validation failed: {str(e)}")


class UnderstandProductRequest(BaseModel):
    """
    Input for ProductUnderstandingAgent.

    validated_features : output of FeatureValidator
        [{ "id": str, "name": str, "description": str,
           "confidence": float, "merge_of": [str] }]
    """
    validated_features: List[Dict[str, Any]]


@app.post("/understand-product")
async def understand_product_endpoint(request: UnderstandProductRequest):
    """
    Run ProductUnderstandingAgent on validated features.

    Input : { "validated_features": [ ...ValidatedFeature list... ] }
    Output: { "status": "success", "data": { "product": { "name", "summary", "core_capabilities" } } }
    """
    from app.analysis.product_understanding_agent import understand_product
    try:
        result = understand_product(request.validated_features)
        return {"status": "success", "data": result.model_dump()}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Product understanding failed: {str(e)}")


class GenerateRequirementsRequest(BaseModel):
    """
    Input for FunctionalRequirementGenerator.

    validated_features : output of FeatureValidator
        [{ "id": str, "name": str, "description": str,
           "confidence": float, "merge_of": [str] }]
    """
    validated_features: List[Dict[str, Any]]


@app.post("/generate-requirements")
async def generate_requirements_endpoint(request: GenerateRequirementsRequest):
    """
    Generate 1–3 testable functional requirements per validated feature.

    Input : { "validated_features": [ ...ValidatedFeature list... ] }
    Output: { "status": "success", "data": { "functional_requirements": [...] } }
    """
    from app.analysis.functional_requirement_generator import generate_requirements
    try:
        result = generate_requirements(request.validated_features)
        return {"status": "success", "data": result.model_dump()}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Requirement generation failed: {str(e)}")


class GenerateNFRsRequest(BaseModel):
    """
    Input for NonFunctionalRequirementGenerator.

    validated_features : output of FeatureValidator
        [{ "id": str, "name": str, "description": str,
           "confidence": float, "merge_of": [str] }]
    product_name : optional snake_case archetype from ProductUnderstandingAgent
    """
    validated_features: List[Dict[str, Any]]
    product_name: Optional[str] = ""


@app.post("/generate-nfrs")
async def generate_nfrs_endpoint(request: GenerateNFRsRequest):
    """
    Infer 5–8 non-functional requirements from validated feature signals.

    Input : { "validated_features": [...], "product_name": "social_platform" }
    Output: { "status": "success", "data": { "non_functional_requirements": [...] } }
    """
    from app.analysis.non_functional_requirement_generator import generate_nfrs
    try:
        result = generate_nfrs(
            request.validated_features,
            product_name=request.product_name or "",
        )
        return {"status": "success", "data": result.model_dump()}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"NFR generation failed: {str(e)}")


class ComposeBRDRequest(BaseModel):
    """Input for BRDComposer."""
    product_data: Dict[str, Any]
    features_data: Dict[str, Any]
    fr_data: Dict[str, Any]
    nfr_data: Dict[str, Any]


@app.post("/compose-brd")
async def compose_brd_endpoint(request: ComposeBRDRequest):
    """
    Assemble the four intermediate JSON analysis results into a formatted Markdown BRD.

    Returns: { "status": "success", "data": "<markdown string>" }
    """
    from app.analysis.brd_composer import compose_brd
    try:
        _prod = request.product_data
        biz_ctx = _prod.get("business_context", _prod.get("product", _prod))
        feat_list = request.features_data.get("validated_features", request.features_data.get("features", []))
        fr_list = request.fr_data.get("functional_requirements", [])
        nfr_list = request.nfr_data.get("non_functional_requirements", [])
        markdown_str = compose_brd(
            business_context=biz_ctx,
            features=feat_list,
            functional_requirements=fr_list,
            non_functional_requirements=nfr_list,
        )
        return {"status": "success", "data": markdown_str}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"BRD composition failed: {str(e)}")


class ValidateBRDRequest(BaseModel):
    """Input for BRDValidator."""
    brd_markdown: str


@app.post("/validate-brd")
async def validate_brd_endpoint(request: ValidateBRDRequest):
    """
    Score a generated BRD document deterministically.
    Flags revision if the completeness/consistency/clarity score < 0.85.

    Returns: { "status": "success", "data": BRDValidationResult }
    """
    from app.analysis.brd_validator import validate_brd
    try:
        result = validate_brd(request.brd_markdown, [], [])
        return {"status": "success", "data": result.model_dump()}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"BRD validation failed: {str(e)}")


class FixBRDRequest(BaseModel):
    """Input for BRDFixLoop."""
    initial_brd_markdown: str


@app.post("/fix-brd")
async def fix_brd_endpoint(request: FixBRDRequest):
    from app.analysis.brd_fix_loop import run_fix_loop
    try:
        result = run_fix_loop(request.initial_brd_markdown)
        return {"status": "success", "data": result}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"BRD fix loop failed: {str(e)}")


# ---------------------------------------------------------------------------
# Download endpoints
# ---------------------------------------------------------------------------

class DownloadBRDRequest(BaseModel):
    """Input for BRD download endpoints."""
    brd_markdown: str
    filename: Optional[str] = "brd_output"


@app.post("/download/brd-markdown")
async def download_brd_markdown(request: DownloadBRDRequest):
    """
    Stream the BRD Markdown content as a downloadable .md file.
    Input : { "brd_markdown": "...", "filename": "brd_output" }
    """
    from fastapi.responses import Response
    content = request.brd_markdown.encode("utf-8")
    filename = (request.filename or "brd_output").replace(" ", "_")
    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}.md"'},
    )


@app.post("/download/brd-docx")
async def download_brd_docx(request: DownloadBRDRequest):
    """
    Convert BRD Markdown to .docx and stream it as a downloadable file.
    Requires python-docx to be installed.
    Input : { "brd_markdown": "...", "filename": "brd_output" }
    """
    import tempfile
    from fastapi.responses import FileResponse
    from app.analysis.document_generator import markdown_to_docx
    from pathlib import Path

    filename = (request.filename or "brd_output").replace(" ", "_")
    try:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        markdown_to_docx(request.brd_markdown, tmp_path)

        return FileResponse(
            path=str(tmp_path),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"{filename}.docx",
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"DOCX generation failed: {str(e)}")


@app.post("/download/pipeline-json")
async def download_pipeline_json(payload: Dict[str, Any]):
    """
    Stream raw pipeline JSON as a downloadable .json file.
    Input : the pipeline payload dict directly.
    """
    import json as _json
    from fastapi.responses import Response
    content = _json.dumps(payload, indent=2).encode("utf-8")
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="pipeline_output.json"'},
    )

