from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from matini.schemas import bases
from matini.schemas.evidence import AssessmentProfile


class BaseLLM(BaseModel):
    name: str
    provider: Literal["ollama"] = "ollama"
    # Empty base_url falls back to settings.ollama_base_url (see routers/llms.py).
    base_url: str = ""
    model_name: str  # the Ollama model tag, e.g. "llama3.1"
    description: str = ""
    # Model size in billions of parameters (e.g. 3.2 for a 3.2B model); None = unknown.
    parameter_size_b: Optional[float] = Field(default=None, gt=0)
    status: Literal["active", "inactive", "delete"] = "active"


class CreateUpdateLLM(BaseLLM):
    pass


class LLM(bases.BaseSchema, BaseLLM):
    # Deliberately not in CreateUpdateLLM: editing or toggling an LLM must not touch the profile
    # (it has its own endpoint, PUT /llms/update/{id}/profile).
    assessment_profile: AssessmentProfile = Field(default_factory=AssessmentProfile)


class LLMList(BaseModel):
    llms: List[LLM] = Field(default_factory=list)


class LLMTestResult(BaseModel):
    ok: bool
    reply: Optional[str] = None
    error: Optional[str] = None
    latency_ms: float = 0.0
