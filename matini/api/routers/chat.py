import datetime
import json
from typing import AsyncIterator

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException
from fastapi import status as http_status
from fastapi.responses import StreamingResponse

from matini import models, schemas
from matini.api.routers.llms import effective_base_url, get_llm_or_404
from matini.api.services import local_llm

router = APIRouter(prefix="/conversations", tags=["Chat"])

TITLE_MAX_LEN = 60


async def get_conversation_or_404(conversation_id: PydanticObjectId) -> models.Conversation:
    conversation = await models.Conversation.find_one(
        models.Conversation.id == conversation_id, models.Conversation.status != "delete"
    )
    if not conversation:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Not found conversation")
    return conversation


@router.get("")
async def get_all() -> schemas.conversations.ConversationList:
    conversations = await models.Conversation.find({"status": "active"}).sort("-updated_date").to_list()
    return schemas.conversations.ConversationList(conversations=conversations)


@router.post("/create")
async def create(form: schemas.conversations.CreateConversation) -> schemas.conversations.Conversation:
    conversation = models.Conversation(llm_id=form.llm_id)
    await conversation.insert()
    return conversation


@router.get("/{conversation_id}")
async def get(conversation_id: PydanticObjectId) -> schemas.conversations.Conversation:
    return await get_conversation_or_404(conversation_id)


@router.delete("/delete/{conversation_id}")
async def delete(conversation_id: PydanticObjectId) -> schemas.conversations.Conversation:
    conversation = await get_conversation_or_404(conversation_id)
    conversation.status = "delete"
    conversation.updated_date = datetime.datetime.now()
    await conversation.save()
    return conversation


def _ndjson(payload: dict) -> bytes:
    return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: PydanticObjectId, form: schemas.conversations.SendMessageRequest
) -> StreamingResponse:
    """Append the user's message, stream the model's reply as NDJSON, then save the reply.

    Stream lines: {"delta": "..."} repeated, then {"done": true} or {"error": "..."}.
    """
    content = form.content.strip()
    if not content:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty message")

    conversation = await get_conversation_or_404(conversation_id)
    llm = await get_llm_or_404(form.llm_id)

    if not conversation.messages:
        conversation.title = content[:TITLE_MAX_LEN]
    conversation.llm_id = llm.id
    conversation.messages.append(schemas.conversations.Message(role="user", content=content))
    conversation.updated_date = datetime.datetime.now()
    await conversation.save()

    history = [{"role": m.role, "content": m.content} for m in conversation.messages]
    base_url = effective_base_url(llm)
    model_name = llm.model_name

    async def stream() -> AsyncIterator[bytes]:
        parts: list[str] = []
        try:
            async for delta in local_llm.chat_stream(model_name, history, base_url=base_url):
                parts.append(delta)
                yield _ndjson({"delta": delta})
        except local_llm.OllamaUnavailableError as exc:
            yield _ndjson({"error": str(exc)})
        finally:
            # Keep whatever was generated, even if the client disconnected or Ollama failed midway.
            if parts:
                conversation.messages.append(
                    schemas.conversations.Message(role="assistant", content="".join(parts))
                )
                conversation.updated_date = datetime.datetime.now()
                await conversation.save()
        yield _ndjson({"done": True})

    return StreamingResponse(stream(), media_type="application/x-ndjson")
