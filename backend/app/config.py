"""Settings from the environment (.env at the repo root).

Nothing marked TO DECIDE in the plan has a default here. The app refuses to
start until those values are set, and names the ones that are missing.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"

# What the web app needs before it will start.
APP_REQUIRED = (
    "OPENROUTER_API_KEY",
    "MODEL_A_ID",
    "MODEL_B_ID",
    "SUPABASE_DB_URL",
    "CONFIDENCE_THRESHOLD",
    "MIN_RETURNS_TO_FLAG",
    "LIFT_THRESHOLD",
)
# eval.py runs before CONFIDENCE_THRESHOLD is decided (it is how we decide it).
EVAL_REQUIRED = ("OPENROUTER_API_KEY", "MODEL_A_ID", "MODEL_B_ID", "SUPABASE_DB_URL")
DB_REQUIRED = ("SUPABASE_DB_URL",)


class ConfigError(RuntimeError):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    OPENROUTER_API_KEY: Optional[str] = None
    MODEL_A_ID: Optional[str] = None
    MODEL_B_ID: Optional[str] = None
    SUPABASE_DB_URL: Optional[str] = None
    CONFIDENCE_THRESHOLD: Optional[float] = Field(default=None, ge=0, le=1)
    MIN_RETURNS_TO_FLAG: Optional[int] = Field(default=None, ge=1)
    LIFT_THRESHOLD: Optional[float] = Field(default=None, gt=0)

    FRONTEND_ORIGINS: str = "http://localhost:3000"
    JUNK_MIN_CHARS: int = Field(default=3, ge=1)
    CLASSIFY_CONCURRENCY: int = Field(default=8, ge=1, le=64)

    MODEL_A_INPUT_USD_PER_MTOK: Optional[float] = Field(default=None, ge=0)
    MODEL_A_OUTPUT_USD_PER_MTOK: Optional[float] = Field(default=None, ge=0)
    MODEL_B_INPUT_USD_PER_MTOK: Optional[float] = Field(default=None, ge=0)
    MODEL_B_OUTPUT_USD_PER_MTOK: Optional[float] = Field(default=None, ge=0)

    @field_validator("*", mode="before")
    @classmethod
    def _blank_means_unset(cls, value, info):
        # `KEY=` in .env arrives as "", which should behave like the key being absent.
        if isinstance(value, str) and not value.strip():
            return cls.model_fields[info.field_name].default
        return value.strip() if isinstance(value, str) else value

    @property
    def frontend_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.FRONTEND_ORIGINS.split(",") if o.strip()]


@lru_cache
def _load() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        bad = sorted({str(err["loc"][0]) for err in exc.errors()})
        raise ConfigError(f"Invalid value in {ENV_FILE} for: {', '.join(bad)}") from None


def get_settings(required: tuple[str, ...] = APP_REQUIRED) -> Settings:
    settings = _load()
    missing = [name for name in required if getattr(settings, name) is None]
    if missing:
        raise ConfigError(
            f"Missing config: {', '.join(missing)}. Set them in {ENV_FILE} (see .env.example)."
        )
    return settings
