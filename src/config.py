from typing import Annotated, List
import os

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(_BASE_DIR, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str
    TARGET_CHANNEL_ID: str
    ADMIN_IDS: Annotated[List[int], NoDecode] = Field(default_factory=list)

    TELEGRAM_API_ID: int
    TELEGRAM_API_HASH: str
    TELEGRAM_SESSION_NAME: str = "sessions/tyrobota_collector"

    AI_PROVIDER: str = "openai"
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"
    AI_TEMPERATURE: float = 0.1
    AI_TIMEOUT_SECONDS: int = 30

    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"

    MIN_PUBLISH_SCORE: int = 70
    MIN_TEXT_LENGTH: int = 40
    MAX_TEXT_LENGTH: int = 4000
    DEDUP_SIMILARITY_THRESHOLD: float = 0.82
    POLL_INTERVAL_SECONDS: int = 60

    QUIET_START_HOUR: int = 21
    QUIET_START_MINUTE: int = 45
    QUIET_END_HOUR: int = 8
    QUIET_END_MINUTE: int = 0
    QUIET_TZ: str = "Europe/Kyiv"

    QUIET_ANNOUNCE: str = "🌙 анал переходить у нічний режим — нові вакансії не публікуються до 08:00 ранку. екаємо вас зранку! 💤"
    QUIET_ANNOUNCE_BEFORE_MIN: int = 15
    QUIET_GRACE_MIN: int = 60
    QUIET_STALE_SKIP_HOURS: int = 3

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if v is None:
            return []

        if isinstance(v, int):
            return [v]

        if isinstance(v, float):
            return [int(v)]

        if isinstance(v, (list, tuple)):
            out = []
            for x in v:
                try:
                    out.append(int(str(x).strip()))
                except (ValueError, TypeError):
                    continue
            return out

        if isinstance(v, str):
            s = v.strip()

            if not s:
                return []

            if s.startswith("["):
                import json as _json
                try:
                    parsed = _json.loads(s)
                    if isinstance(parsed, (list, tuple)):
                        return [int(x) for x in parsed]
                    return [int(parsed)]
                except (ValueError, TypeError):
                    pass

            return [
                int(x.strip())
                for x in s.split(",")
                if x.strip().lstrip("-").isdigit()
            ]

        return []

    @field_validator("QUIET_START_HOUR", "QUIET_END_HOUR", mode="before")
    @classmethod
    def check_hour(cls, v):
        iv = int(v)
        if not 0 <= iv <= 23:
            raise ValueError(f"hour must be 0..23, got {iv}")
        return iv

    @field_validator("QUIET_START_MINUTE", "QUIET_END_MINUTE", mode="before")
    @classmethod
    def check_minute(cls, v):
        iv = int(v)
        if not 0 <= iv <= 59:
            raise ValueError(f"minute must be 0..59, got {iv}")
        return iv


settings = Settings()
