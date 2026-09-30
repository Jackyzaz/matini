import datetime

from beanie import Document, PydanticObjectId
from pydantic import Field

from matini.schemas.evidence import BaseEvidenceFile

MAX_EXTRACTED_CHARS = 50_000


class EvidenceFile(BaseEvidenceFile, Document):
    id: PydanticObjectId = Field(default_factory=PydanticObjectId, alias="_id")

    # Stored inline: uploads are capped at 8 MB, under BSON's 16 MB document limit, so no GridFS.
    data: bytes = b""
    extracted_text: str = ""
    created_date: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Settings:
        name = "evidence_files"
        indexes = ["llm_id"]
