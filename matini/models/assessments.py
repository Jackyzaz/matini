from beanie import Document, PydanticObjectId
from pydantic import Field

from matini.schemas.assessment import AssessmentReport as AssessmentReportSchema


class Assessment(AssessmentReportSchema, Document):
    id: PydanticObjectId = Field(default_factory=PydanticObjectId, alias="_id")

    class Settings:
        name = "assessments"
        indexes = ["llm_id"]
