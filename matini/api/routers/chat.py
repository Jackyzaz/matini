from fastapi import APIRouter, HTTPException
from matini.api.schemas.chat import ChatRequest, ChatResponse
from matini.api.services.guardrails import process_chat

router = APIRouter(prefix="/chat", tags=["Sandboxed Chat & Guardrails"])

@router.post("", response_model=ChatResponse)
async def chat_with_guardrail(request: ChatRequest):
    """
    Executes prompt through active model guardrails:
    1. Rule-based keyword filtering
    2. LLM-as-a-judge intent & injection inspection
    3. Mock Sandboxed LLM response generation
    """
    result = process_chat(request.model_id, request.prompt)
    if result.status == "error":
        raise HTTPException(status_code=404, detail="Target AI model not found in registry")
    return result
