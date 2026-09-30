from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_title: str = "Matini AI Registry API"
    app_version: str = "0.1.0"
    api_prefix: str = "/api"
    cors_origins: list[str] = ["*"]

    # --- NIST AI RMF Ethical Assessment POC: local LLM (Ollama) connection ---
    # Points at wherever Ollama is actually running. Keep this on 127.0.0.1 while
    # testing on this machine; when you move Ollama to another machine, set
    # OLLAMA_BASE_URL=http://<that machine's LAN IP>:11434 in your .env (see
    # docs/nist-rmf-poc-guide.md for the full setup walkthrough).
    ollama_base_url: str = "http://127.0.0.1:11434"

    # Model used as the "judge" that scores each NIST AI RMF criterion.
    ollama_judge_model: str = "llama3.1"

    # Default model used as the "subject" being assessed / probed, when a
    # registry entry doesn't specify its own AIModel.ollama_model_name.
    ollama_subject_model: str = "llama3.1"

    # Ollama on CPU-only or modest hardware can be slow; keep this generous.
    ollama_timeout_s: float = 120.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
