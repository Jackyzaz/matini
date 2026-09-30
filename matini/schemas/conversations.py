import datetime
from typing import List, Literal, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from matini.schemas import bases


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_date: datetime.datetime = Field(default_factory=datetime.datetime.now)


class BaseConversation(BaseModel):
    title: str = "New chat"
    llm_id: Optional[PydanticObjectId] = None
    messages: List[Message] = Field(default_factory=list)
    status: Literal["active", "delete"] = "active"


class CreateConversation(BaseModel):
    llm_id: Optional[PydanticObjectId] = None


class Conversation(bases.BaseSchema, BaseConversation):
    created_date: datetime.datetime = Field(default_factory=datetime.datetime.now)
    updated_date: datetime.datetime = Field(default_factory=datetime.datetime.now)


class ConversationSummary(bases.BaseSchema):
    title: str
    llm_id: Optional[PydanticObjectId] = None
    updated_date: datetime.datetime


class ConversationList(BaseModel):
    conversations: List[ConversationSummary] = Field(default_factory=list)


class SendMessageRequest(BaseModel):
    content: str
    llm_id: PydanticObjectId
