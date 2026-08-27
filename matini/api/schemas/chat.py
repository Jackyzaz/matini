from pydantic import BaseModel
from typing import List, Optional

class ChatRequest(BaseModel):
    model_id: str
    prompt: str

class GuardrailCheckResult(BaseModel):
    layer: str
    passed: bool
    reason: Optional[str] = None
    latency_ms: float
    detected_triggers: Optional[List[str]] = None

class ChatResponse(BaseModel):
    model_id: str
    prompt: str
    response: Optional[str] = None
    status: str  # allowed, blocked
    guardrail_results: List[GuardrailCheckResult]
    total_latency_ms: float
