from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: PydanticObjectId = Field(default_factory=PydanticObjectId)
