from typing import List

from fastapi import APIRouter, HTTPException

from matini.api.schemas.assessment import AssessmentCriterion, AssessmentReport, RunAssessmentRequest
from matini.api.services import assessment as assessment_service
from matini.api.services.nist_rmf import get_criteria
from matini.api.services.registry import get_model_by_id

router = APIRouter(prefix="/assessment", tags=["NIST AI RMF Ethical Assessment (POC)"])


@router.get("/criteria", response_model=List[AssessmentCriterion])
async def list_criteria():
    """Return the static NIST AI RMF-derived criteria set used by this POC."""
    return get_criteria()


@router.post("/{model_id}/run", response_model=AssessmentReport)
async def run(model_id: str, request: RunAssessmentRequest):
    """Run (or re-run) the NIST AI RMF assessment against a registered model,
    using a local LLM (via Ollama) as both the probed subject and the judge."""
    if not get_model_by_id(model_id):
        raise HTTPException(status_code=404, detail="Model not found")
    try:
        return assessment_service.run_assessment(model_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{model_id}", response_model=AssessmentReport)
async def latest(model_id: str):
    report = assessment_service.get_latest_report(model_id)
    if not report:
        raise HTTPException(status_code=404, detail="No assessment run yet for this model")
    return report


@router.get("/{model_id}/history", response_model=List[AssessmentReport])
async def history(model_id: str):
    return assessment_service.get_history(model_id)
