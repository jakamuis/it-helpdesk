from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = Field(default="http://ollama:11434", min_length=1)
    ollama_model: str = Field(default="qwen3:0.6b", min_length=1, max_length=128)
    ollama_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    ollama_timeout_seconds: int = Field(default=25, ge=1, le=55)
    ollama_think: bool = False
    ollama_num_predict: int = Field(default=256, ge=8, le=4096)
    ollama_compact_mode: bool = True
    ai_confidence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    ai_audit_db_path: str = Field(default="/data/ai_triage_audit.db", min_length=1)


settings = Settings()
