import asyncio
from urllib.parse import quote

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi import status as http_status
from fastapi.responses import Response

from matini import models, schemas
from matini.api.routers.llms import get_llm_or_404
from matini.api.services import evidence_text

router = APIRouter(prefix="/evidence-files", tags=["Evidence files"])

MAX_FILE_BYTES = 8 * 1024 * 1024  # under BSON's 16 MB document limit, so files live inline (no GridFS)
PREVIEW_CHARS = 2000


async def get_file_or_404(file_id: PydanticObjectId) -> models.EvidenceFile:
    file = await models.EvidenceFile.find_one(models.EvidenceFile.id == file_id, models.EvidenceFile.status != "delete")
    if not file:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Not found file")
    return file


def to_metadata(file: models.EvidenceFile) -> schemas.evidence.EvidenceFile:
    return schemas.evidence.EvidenceFile(
        **file.model_dump(include=set(schemas.evidence.BaseEvidenceFile.model_fields) | {"id", "created_date"}),
        has_text=bool(file.extracted_text),
    )


@router.post("/upload")
async def upload(file: UploadFile, llm_id: PydanticObjectId = Query()) -> schemas.evidence.EvidenceFile:
    await get_llm_or_404(llm_id)
    filename = file.filename or "file"
    if not evidence_text.is_supported(filename):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="รองรับเฉพาะไฟล์ PDF, DOCX, TXT และ MD",
        )
    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"ไฟล์ใหญ่เกิน {MAX_FILE_BYTES // (1024 * 1024)} MB",
        )
    content_type = file.content_type or "application/octet-stream"
    text, error = await asyncio.to_thread(evidence_text.extract_text, filename, content_type, data)

    doc = models.EvidenceFile(
        llm_id=llm_id,
        filename=filename,
        content_type=content_type,
        size=len(data),
        data=data,
        extracted_text=text,
        extract_error=error,
    )
    await doc.insert()
    return to_metadata(doc)


@router.get("/{file_id}")
async def get(file_id: PydanticObjectId, full: bool = False) -> schemas.evidence.EvidenceFileDetail:
    """Metadata plus a preview of the extracted text; `full=true` returns all of it (what the human assessor reads)."""
    file = await get_file_or_404(file_id)
    text = file.extracted_text if full else file.extracted_text[:PREVIEW_CHARS]
    return schemas.evidence.EvidenceFileDetail(**to_metadata(file).model_dump(), text_preview=text)


@router.get("/{file_id}/download")
async def download(file_id: PydanticObjectId, inline: bool = False) -> Response:
    """The original file. `inline=true` lets the browser show it in place (a PDF in an iframe)."""
    file = await get_file_or_404(file_id)
    disposition = "inline" if inline else "attachment"
    return Response(
        content=file.data,
        media_type=file.content_type or "application/octet-stream",
        headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(file.filename)}"},
    )


@router.delete("/delete/{file_id}")
async def delete(file_id: PydanticObjectId) -> schemas.evidence.EvidenceFile:
    file = await get_file_or_404(file_id)
    file.status = "delete"
    await file.save()
    return to_metadata(file)
