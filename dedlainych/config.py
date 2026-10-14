from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    bot_token: SecretStr = SecretStr("")
    database_url: SecretStr = SecretStr("postgresql+asyncpg://dedlainych:CHANGE_ME@db/dedlainych")
    admin_ids: list[int] = Field(default_factory=list)
    ai_provider: str = "rules"
    ai_api_key: SecretStr = SecretStr("")
    ai_base_url: str = "http://localhost:11434"
    ai_model: str = "qwen2.5:7b"
    tz: str = "Asia/Yakutsk"
    group_code: str = "6104-ОБ"
    instance_lock_wait_seconds: int = Field(default=0, ge=0, le=600)
    max_file_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)

    @field_validator("tz")
    @classmethod
    def timezone_valid(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @field_validator("ai_provider")
    @classmethod
    def provider_valid(cls, value: str) -> str:
        if value not in {"rules", "ollama"}:
            raise ValueError("Доступны rules и ollama; платные API не включены")
        return value


@lru_cache
def settings() -> Settings:
    return Settings()
