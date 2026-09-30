import datetime

from beanie import Document, PydanticObjectId
from pydantic import Field

from matini.schemas.llms import LLM as LLMSchema


class LLM(LLMSchema, Document):
    id: PydanticObjectId = Field(default_factory=PydanticObjectId, alias="_id")

    created_date: datetime.datetime = Field(default_factory=datetime.datetime.now)
    updated_date: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Settings:
        name = "llms"
