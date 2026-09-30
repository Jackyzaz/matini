from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from matini.models import sanitize_mongo_uri


class Settings(BaseSettings):
    app_title: str = "Matini"
    app_version: str = "0.1.0"
    api_prefix: str = "/api"
    cors_origins: list[str] = ["*"]

    # MongoDB (Beanie). The database name is taken from the URI path.
    mongodb_uri: str = "mongodb://localhost:27017/matinidb"

    @field_validator("mongodb_uri", mode="before")
    @classmethod
    def validate_mongodb_uri(cls, v: str) -> str:
        return sanitize_mongo_uri(v)

    # Default Ollama endpoint. Used as an LLM's base_url when the admin form leaves
    # it empty (this applies to assessment subjects and judges alike). Keep it on
    # 127.0.0.1 when Ollama runs on this machine; otherwise point it at the other
    # machine's LAN IP, e.g. OLLAMA_BASE_URL=http://192.168.1.20:11434
    ollama_base_url: str = "http://127.0.0.1:11434"

    # Ollama on CPU-only or modest hardware can be slow; keep this generous.
    ollama_timeout_s: float = 120.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
