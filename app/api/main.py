from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import traceback
import os

# Load environment variables from .env at startup so OPENAI_API_KEY
# and other secrets are available to all pipeline modules.
try:
    from dotenv import load_dotenv
    from pathlib import Path as _Path
    _env_path = _Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(dotenv_path=_env_path, override=False)  # override=False: OS env vars take priority
except ImportError:
    pass  # python-dotenv not installed; rely on shell environment

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
      - validation: validation results
    """
    from app.pipeline.runner import run_full_pipeline_service
    from app.analysis.payload_converter import build_brd

    try:
        output_dir = request.output_path if request.output_path else "runtime/pipeline_out"
        result = run_full_pipeline_service(
            repo_url=request.repo_url,
            output_dir=output_dir,
        )

        final_payload = result["final_payload"]
        final_markdown = result["final_markdown"]
        final_validation = result["final_validation"]

        # Build MinimalBRD for structural response
        brd_struct = build_brd(final_payload)

        return {
            "status": "success",
            "pipeline": final_payload,
            "brd": brd_struct.model_dump(),
            "markdown": final_markdown,
            "validation": final_validation
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
            system_type=request.product_name or "",
            tech_stack=[]
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
    from fastapi.responses import FileResponse
    from app.analysis.document_generator import markdown_to_docx
    from pathlib import Path

    filename = (request.filename or "brd_output").replace(" ", "_")
    try:
        # Save directly to the pipeline_out directory instead of a system temp folder
        out_dir = Path("runtime/pipeline_out")
        out_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = out_dir / f"{filename}.docx"

        markdown_to_docx(request.brd_markdown, file_path)

        return FileResponse(
            path=str(file_path),
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


# ─── Skill Pack Management Endpoints ──────────────────────────────────────────

@app.get("/skills")
async def list_skill_packs():
    """
    List all available skill packs (both curated and auto-generated).
    Returns: id, name, description, auto_generated flag, and script count.
    """
    try:
        from app.skills.skill_loader import load_all_skills
        skills = load_all_skills()
        return {
            "skill_packs": [
                {
                    "id": s.id,
                    "name": s.name,
                    "version": s.version,
                    "description": s.description[:300],
                    "auto_generated": s.auto_generated,
                    "has_scripts": s.has_scripts,
                    "script_count": len(s.script_names),
                    "detection_signals": s.detection_signals,
                    "nfr_emphasis": s.nfr_emphasis,
                }
                for s in skills
            ],
            "total": len(skills),
            "curated": sum(1 for s in skills if not s.auto_generated),
            "generated": sum(1 for s in skills if s.auto_generated),
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to load skill packs: {str(e)}")


@app.get("/skills/{skill_id}")
async def get_skill_pack(skill_id: str):
    """
    Get full details of a specific skill pack, including its SKILL.md content.
    """
    try:
        from app.skills.skill_loader import load_all_skills
        skills = load_all_skills()
        for s in skills:
            if s.id == skill_id:
                return {
                    "id": s.id,
                    "name": s.name,
                    "version": s.version,
                    "description": s.description,
                    "auto_generated": s.auto_generated,
                    "has_scripts": s.has_scripts,
                    "script_names": s.script_names,
                    "detection_signals": s.detection_signals,
                    "nfr_emphasis": s.nfr_emphasis,
                    "brd_section_notes": s.brd_section_notes,
                    "memory_tags": s.memory_tags,
                    "instructions_body": s.instructions_body,
                }
        raise HTTPException(status_code=404, detail=f"Skill pack '{skill_id}' not found")
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


class SkillComposeRequest(BaseModel):
    """Request body for manually triggering skill composition."""
    evidence: Dict[str, Any]
    repo_context: Dict[str, Any]
    detected_deps: List[Dict[str, Any]] = []


@app.post("/skills/compose")
async def compose_skill_pack(request: SkillComposeRequest):
    """
    Manually trigger skill pack composition via LLM.
    Provide evidence and repo_context from a previous pipeline run.
    The generated skill pack is saved to packs/_generated/ for future reuse.
    """
    try:
        from app.skills.skill_composer import compose_missing_skill
        result = compose_missing_skill(
            request.evidence,
            request.repo_context,
            request.detected_deps,
        )
        if result:
            return {
                "status": "success",
                "skill_id": result.id,
                "name": result.name,
                "description": result.description,
                "has_scripts": result.has_scripts,
                "auto_generated": True,
            }
        else:
            return {
                "status": "failed",
                "message": "Skill composition failed — check OPENAI_API_KEY or LLM availability",
            }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Skill composition failed: {str(e)}")


@app.put("/skills/{skill_id}/promote")
async def promote_skill_pack(skill_id: str):
    """
    Promote an auto-generated skill pack from _generated/ to the stable packs/ directory.
    This makes it a first-class curated skill pack.
    """
    import shutil
    try:
        from app.skills.skill_loader import PACKS_DIR, GENERATED_DIR
        source = None
        if GENERATED_DIR.is_dir():
            for child in GENERATED_DIR.iterdir():
                if child.is_dir() and child.name == skill_id:
                    source = child
                    break
        if not source:
            raise HTTPException(status_code=404, detail=f"Generated skill '{skill_id}' not found")

        dest = PACKS_DIR / skill_id
        if dest.exists():
            raise HTTPException(status_code=409, detail=f"Stable skill '{skill_id}' already exists")

        shutil.copytree(source, dest)
        shutil.rmtree(source)
        return {
            "status": "promoted",
            "skill_id": skill_id,
            "from": str(source),
            "to": str(dest),
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

