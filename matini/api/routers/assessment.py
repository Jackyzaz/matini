from typing import List

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException
from fastapi import status as http_status

from matini import schemas
from matini.api.routers.llms import get_llm_or_404
from matini.api.services import assessment as assessment_service
from matini.api.services.nist_rmf import get_criteria

router = APIRouter(prefix="/assessment", tags=["NIST AI RMF Assessment"])


@router.get("/criteria")
async def list_criteria() -> List[schemas.assessment.AssessmentCriterion]:
    """Return the static NIST AI RMF-derived criteria set."""
    return get_criteria()


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> schemas.assessment.AssessmentJob:
    job = assessment_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Not found job")
    return job


@router.post("/{llm_id}/run")
async def run(
    llm_id: PydanticObjectId, form: schemas.assessment.RunAssessmentRequest
) -> schemas.assessment.AssessmentJob:
    """Start an assessment of a registered LLM in the background; poll /jobs/{job_id} for progress."""
    llm = await get_llm_or_404(llm_id)
    return assessment_service.start_assessment(llm, form)


@router.get("/{llm_id}")
async def latest(llm_id: PydanticObjectId) -> schemas.assessment.AssessmentReport:
    report = await assessment_service.get_latest_report(llm_id)
    if not report:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="No assessment run yet for this LLM")
    return report


@router.get("/{llm_id}/history")
async def history(llm_id: PydanticObjectId) -> List[schemas.assessment.AssessmentReport]:
    return await assessment_service.get_history(llm_id)
