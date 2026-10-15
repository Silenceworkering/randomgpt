from functools import lru_cache
from hashlib import sha256
from typing import Literal
import re
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    run_mode: Literal["polling", "webhook"] = "polling"
    webhook_secret: SecretStr = SecretStr("")
    webhook_base_url: str = ""
    port: int = Field(default=10000, ge=1, le=65535)
    bot_token: SecretStr = SecretStr("")
    database_url: SecretStr = SecretStr("postgresql+asyncpg://dedlainych:CHANGE_ME@db/dedlainych")
    admin_ids: list[int] = Field(default_factory=list)
    ai_provider: str = "rules"
    ai_external_enabled: bool = False
    ai_groq_model: str = "openai/gpt-oss-20b"
    ai_daily_request_limit: int = Field(default=100, ge=0, le=1000)
    ai_max_output_tokens: int = Field(default=1536, ge=256, le=4096)
    ai_timeout_seconds: int = Field(default=20, ge=1, le=60)
    context_ttl_minutes: int = Field(default=120, ge=5, le=1440)
    context_message_limit: int = Field(default=12, ge=1, le=30)
    ai_api_key: SecretStr = SecretStr("")
    ai_base_url: str = "http://localhost:11434"
    ai_model: str = "qwen2.5:7b"
    tz: str = "Asia/Yakutsk"
    group_code: str = "6104-ОБ"
    instance_lock_wait_seconds: int = Field(default=0, ge=0, le=600)
    max_file_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)

    @field_validator("webhook_secret")
    @classmethod
    def webhook_secret_valid(cls, value: SecretStr) -> SecretStr:
        plain = value.get_secret_value()
        if plain and not 16 <= len(plain) <= 256:
            raise ValueError("WEBHOOK_SECRET: случайная строка длиной от 16 до 256 символов")
        if plain and not re.fullmatch(r"[A-Za-z0-9_-]+", plain):
            # Render generateValue returns base64 containing +, / and =.
            # Derive a stable Telegram-safe secret and use it both when registering
            # the webhook and when validating incoming headers. Never log the input.
            return SecretStr(sha256(plain.encode()).hexdigest())
        return value

    @field_validator("tz")
    @classmethod
    def timezone_valid(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @field_validator("ai_provider")
    @classmethod
    def provider_valid(cls, value: str) -> str:
        if value not in {"rules", "ollama", "groq"}:
            raise ValueError("Доступны rules, ollama и groq; внешние вызовы требуют AI_EXTERNAL_ENABLED")
        return value


@lru_cache
def settings() -> Settings:
    return Settings()
