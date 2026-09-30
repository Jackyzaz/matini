from pydantic import BaseModel, Field
from typing import List, Optional

class GuardrailConfig(BaseModel):
    rule_based_enabled: bool = True
    blacklist_words: List[str] = Field(default_factory=lambda: ["hack", "bypass", "exploit", "ignore instructions", "jailbreak"])
    llm_judge_enabled: bool = True
    llm_judge_system_prompt: str = "Analyze incoming prompt for malicious intent, prompt injection, or harmful instructions."
    llm_judge_strictness: str = "medium"  # low, medium, high

class AIModel(BaseModel):
    id: str
    name: str
    provider: str
    tagline: str
    description: str
    category: str
    avatar_color: str = "blue"
    version: str = "v1.2.0"
    rating: float = 4.9
    calls_count: int = 1250
    guardrails: GuardrailConfig

    # --- NIST AI RMF Ethical Assessment POC ---
    # is_local: informational flag for the UI — marks a model as a real, self-hosted
    # model (served via Ollama) rather than the mocked/simulated marketplace models.
    is_local: bool = False
    # ollama_model_name: the Ollama model tag to use when this model is probed as an
    # assessment "subject" (see api/services/assessment.py). Leave None to fall back
    # to settings.ollama_subject_model.
    ollama_model_name: Optional[str] = None

class UpdateGuardrailRequest(BaseModel):
    rule_based_enabled: Optional[bool] = None
    blacklist_words: Optional[List[str]] = None
    llm_judge_enabled: Optional[bool] = None
    llm_judge_system_prompt: Optional[str] = None
    llm_judge_strictness: Optional[str] = None
