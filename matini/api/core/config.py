from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_title: str = "Matini AI Registry API"
    app_version: str = "0.1.0"
    api_prefix: str = "/api"
    cors_origins: list[str] = ["*"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
