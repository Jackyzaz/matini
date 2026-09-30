import asyncio
import datetime
import time
from typing import Literal

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, Query
from fastapi import status as http_status

from matini import models, schemas
from matini.api.core.config import settings
from matini.api.services import local_llm

router = APIRouter(prefix="/llms", tags=["LLMs"])


async def get_llm_or_404(llm_id: PydanticObjectId) -> models.LLM:
    llm = await models.LLM.find_one(models.LLM.id == llm_id, models.LLM.status != "delete")
    if not llm:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Not found LLM")
    return llm


def effective_base_url(llm: models.LLM) -> str:
    return llm.base_url or settings.ollama_base_url


@router.get("")
async def get_all(
    status: Literal["active", "all"] = Query(default="active"),
) -> schemas.llms.LLMList:
    if status == "all":
        query = {"status": {"$ne": "delete"}}
    else:
        query = {"status": "active"}
    llms = await models.LLM.find(query).sort("created_date").to_list()
    return schemas.llms.LLMList(llms=llms)


@router.get("/defaults")
async def defaults() -> dict:
    """Server-side defaults (from .env) that the admin form pre-fills."""
    return {"ollama_base_url": settings.ollama_base_url, "ollama_judge_model": settings.ollama_judge_model}


@router.get("/{llm_id}")
async def get(llm_id: PydanticObjectId) -> schemas.llms.LLM:
    return await get_llm_or_404(llm_id)


@router.post("/create")
async def create(form: schemas.llms.CreateUpdateLLM) -> schemas.llms.LLM:
    llm = models.LLM(**form.model_dump())
    if form.status == "delete":
        llm.status = "active"
    await llm.insert()
    return llm


@router.put("/update/{llm_id}")
async def update(llm_id: PydanticObjectId, form: schemas.llms.CreateUpdateLLM) -> schemas.llms.LLM:
    llm = await get_llm_or_404(llm_id)
    for key, value in form.model_dump().items():
        setattr(llm, key, value)
    llm.updated_date = datetime.datetime.now()
    await llm.save()
    return llm


@router.delete("/delete/{llm_id}")
async def delete(llm_id: PydanticObjectId) -> schemas.llms.LLM:
    llm = await get_llm_or_404(llm_id)
    llm.status = "delete"
    llm.updated_date = datetime.datetime.now()
    await llm.save()
    return llm


@router.post("/{llm_id}/test")
async def test_connection(llm_id: PydanticObjectId) -> schemas.llms.LLMTestResult:
    """Send a tiny prompt to check that Ollama is reachable and the model tag responds."""
    llm = await get_llm_or_404(llm_id)
    start = time.time()
    try:
        reply = await asyncio.to_thread(
            local_llm.probe_subject,
            "Reply with the single word: ok",
            model=llm.model_name,
            base_url=effective_base_url(llm),
        )
    except local_llm.OllamaUnavailableError as exc:
        return schemas.llms.LLMTestResult(ok=False, error=str(exc), latency_ms=round((time.time() - start) * 1000, 1))
    return schemas.llms.LLMTestResult(
        ok=True, reply=reply.strip()[:200], latency_ms=round((time.time() - start) * 1000, 1)
    )
