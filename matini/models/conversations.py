from beanie import Document, PydanticObjectId
from pydantic import Field

from matini.schemas.conversations import Conversation as ConversationSchema


class Conversation(ConversationSchema, Document):
    id: PydanticObjectId = Field(default_factory=PydanticObjectId, alias="_id")

    class Settings:
        name = "conversations"
        indexes = ["updated_date"]
