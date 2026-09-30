from typing import List

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException
from fastapi import status as http_status

from matini import models, schemas
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
    """Start an assessment of a registered LLM in the background; poll /jobs/{job_id} for progress.

    `llm_id` is the LLM being assessed; `form.judge_llm_id` is the registered LLM that scores it.
    """
    llm = await get_llm_or_404(llm_id)
    judge_llm = await get_llm_or_404(form.judge_llm_id)
    return assessment_service.start_assessment(llm, judge_llm, form)


@router.post("/{llm_id}/manual")
async def start_manual(
    llm_id: PydanticObjectId, form: schemas.assessment.StartManualRequest
) -> schemas.assessment.AssessmentJob:
    """Start a human assessment: creates a draft report and sends the MEASURE probes in the background.

    The draft (`job.report_id`) is ready to be scored once the job is done.
    """
    llm = await get_llm_or_404(llm_id)
    return await assessment_service.start_manual_assessment(llm, form.assessor_name)


async def get_report_or_404(report_id: PydanticObjectId) -> models.Assessment:
    report = await assessment_service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Not found report")
    return report


def require_draft(report: models.Assessment) -> None:
    if report.status != "draft":
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="Report is already completed")


def get_result_or_404(report: models.Assessment, criterion_id: str) -> schemas.assessment.CriterionResult:
    result = assessment_service.find_result(report, criterion_id)
    if not result:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Not found criterion")
    return result


@router.get("/reports/{report_id}")
async def get_report(report_id: PydanticObjectId) -> schemas.assessment.AssessmentReport:
    return await get_report_or_404(report_id)


@router.put("/reports/update/{report_id}/criteria/{criterion_id}")
async def score_criterion(
    report_id: PydanticObjectId, criterion_id: str, form: schemas.assessment.HumanScoreRequest
) -> schemas.assessment.AssessmentReport:
    """Save the human assessor's score and rationale for one criterion of a draft."""
    report = await get_report_or_404(report_id)
    require_draft(report)
    result = get_result_or_404(report, criterion_id)
    result.score = form.score
    result.rationale = form.rationale.strip()
    result.risk_level = (
        assessment_service.risk_from_score(float(form.score)) if form.score else schemas.assessment.RiskLevel.UNSCORED
    )
    await report.save()
    return report


@router.post("/reports/{report_id}/criteria/{criterion_id}/probes/create")
async def create_probe(
    report_id: PydanticObjectId, criterion_id: str, form: schemas.assessment.CreateProbeRequest
) -> schemas.assessment.ProbeResult:
    """Send a prompt the assessor typed to the subject LLM and add it to the criterion (this report only)."""
    report = await get_report_or_404(report_id)
    require_draft(report)
    get_result_or_404(report, criterion_id)
    llm = await get_llm_or_404(report.llm_id)
    probe = await assessment_service.send_probe(form.prompt, llm, source="custom")
    # the model can take minutes to answer: reload so scores saved meanwhile are not overwritten
    report = await get_report_or_404(report_id)
    require_draft(report)
    get_result_or_404(report, criterion_id).probes.append(probe)
    await report.save()
    return probe


@router.post("/reports/{report_id}/criteria/{criterion_id}/probes/{probe_id}/rerun")
async def rerun_probe(
    report_id: PydanticObjectId, criterion_id: str, probe_id: str
) -> schemas.assessment.ProbeResult:
    """Send the probe's prompt again and replace its reply."""
    report = await get_report_or_404(report_id)
    require_draft(report)
    probe = next((p for p in get_result_or_404(report, criterion_id).probes if p.id == probe_id), None)
    if not probe:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Not found probe")
    llm = await get_llm_or_404(report.llm_id)
    fresh = await assessment_service.send_probe(probe.prompt, llm, source=probe.source)
    fresh.id = probe_id
    # reload: scores saved while the model was answering must not be overwritten
    report = await get_report_or_404(report_id)
    require_draft(report)
    probes = get_result_or_404(report, criterion_id).probes
    index = next((i for i, p in enumerate(probes) if p.id == probe_id), None)
    if index is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Not found probe")
    probes[index] = fresh
    await report.save()
    return fresh


@router.delete("/reports/{report_id}/criteria/{criterion_id}/probes/delete/{probe_id}")
async def delete_probe(report_id: PydanticObjectId, criterion_id: str, probe_id: str) -> schemas.assessment.AssessmentReport:
    """Remove a prompt the assessor added; the built-in prompts cannot be removed."""
    report = await get_report_or_404(report_id)
    require_draft(report)
    result = get_result_or_404(report, criterion_id)
    probe = next((p for p in result.probes if p.id == probe_id), None)
    if not probe:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Not found probe")
    if probe.source != "custom":
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Built-in probes cannot be deleted")
    result.probes = [p for p in result.probes if p.id != probe_id]
    await report.save()
    return report


@router.post("/reports/{report_id}/complete")
async def complete(report_id: PydanticObjectId) -> schemas.assessment.AssessmentReport:
    report = await get_report_or_404(report_id)
    require_draft(report)
    missing = assessment_service.missing_scores(report)
    if missing:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ยังไม่ได้ให้คะแนน: " + ", ".join(missing),
        )
    assessment_service.complete_manual(report)
    await report.save()
    return report


@router.delete("/reports/delete/{report_id}")
async def delete_report(report_id: PydanticObjectId) -> schemas.assessment.AssessmentReport:
    """Discard a draft. Finished reports are research data and are kept."""
    report = await get_report_or_404(report_id)
    require_draft(report)
    report.status = "delete"
    await report.save()
    return report


@router.get("/{llm_id}")
async def latest(llm_id: PydanticObjectId) -> schemas.assessment.AssessmentReport:
    report = await assessment_service.get_latest_report(llm_id)
    if not report:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="No assessment run yet for this LLM")
    return report


@router.get("/{llm_id}/history")
async def history(llm_id: PydanticObjectId) -> List[schemas.assessment.AssessmentReport]:
    return await assessment_service.get_history(llm_id)
