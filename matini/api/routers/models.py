from fastapi import APIRouter, HTTPException
from typing import List
from matini.api.schemas.models import AIModel, UpdateGuardrailRequest
from matini.api.services.registry import get_all_models, get_model_by_id, update_model_guardrails

router = APIRouter(prefix="/models", tags=["AI Registry"])

@router.get("", response_model=List[AIModel])
async def list_models():
    """Retrieve all AI models registered in the marketplace."""
    return get_all_models()

@router.get("/{model_id}", response_model=AIModel)
async def get_model(model_id: str):
    """Retrieve details and guardrail configuration for a specific AI model."""
    model = get_model_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model

@router.post("/{model_id}/guardrails", response_model=AIModel)
async def update_guardrails(model_id: str, payload: UpdateGuardrailRequest):
    """Update per-model guardrail policy (Rule-based & LLM Judge)."""
    updated = update_model_guardrails(model_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Model not found")
    return updated
