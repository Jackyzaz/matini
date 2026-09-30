from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from matini.schemas import bases


class BaseLLM(BaseModel):
    name: str
    provider: Literal["ollama"] = "ollama"
    # Empty base_url falls back to settings.ollama_base_url (see routers/llms.py).
    base_url: str = ""
    model_name: str  # the Ollama model tag, e.g. "llama3.1"
    description: str = ""
    status: Literal["active", "inactive", "delete"] = "active"


class CreateUpdateLLM(BaseLLM):
    pass


class LLM(bases.BaseSchema, BaseLLM):
    pass


class LLMList(BaseModel):
    llms: List[LLM] = Field(default_factory=list)


class LLMTestResult(BaseModel):
    ok: bool
    reply: Optional[str] = None
    error: Optional[str] = None
    latency_ms: float = 0.0
