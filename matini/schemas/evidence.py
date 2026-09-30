from datetime import date, datetime
from typing import Dict, List, Literal, Optional
from uuid import uuid4

from beanie import PydanticObjectId
from pydantic import BaseModel, Field


class SystemContext(BaseModel):
    intended_use: str = ""
    target_users: str = ""
    out_of_scope_use: str = ""
    data_sources: str = ""
    deployment_context: str = ""
    notes: str = ""


class EvidenceItem(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    kind: Literal["document", "link", "text"]
    title: str = ""
    url: str = ""
    file_id: Optional[PydanticObjectId] = None  # kind == "document": the uploaded EvidenceFile
    excerpt: str = ""
    doc_date: Optional[date] = None


class CriterionEvidence(BaseModel):
    # Self-declared by whoever fills the profile; the judge is told so.
    status: Literal["implemented", "partial", "not_implemented", "unknown"] = "unknown"
    notes: str = ""
    items: List[EvidenceItem] = Field(default_factory=list)


class AssessmentProfile(BaseModel):
    system_context: SystemContext = Field(default_factory=SystemContext)
    criteria: Dict[str, CriterionEvidence] = Field(default_factory=dict)  # keyed by criterion id
    updated_date: Optional[datetime] = None


class BaseEvidenceFile(BaseModel):
    llm_id: PydanticObjectId
    filename: str
    content_type: str = ""
    size: int = 0
    extract_error: Optional[str] = None
    status: Literal["active", "delete"] = "active"


class EvidenceFile(BaseEvidenceFile):
    """File metadata as returned by the API (never includes the raw bytes)."""

    id: PydanticObjectId = Field(default_factory=PydanticObjectId)
    has_text: bool = False
    created_date: datetime = Field(default_factory=datetime.now)


class EvidenceFileDetail(EvidenceFile):
    text_preview: str = ""
