"""Explicit LM Studio configuration; no model discovery or loading on import."""

import os
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from dotenv import load_dotenv


def load_environment() -> None:
    """Load the subproject's .env on startup; explicit environment takes priority."""
    project_root = Path(__file__).resolve().parents[2]
    # Editable checkout: fixed location, independent of the launch directory.
    # Installed wheel: use only .env in cwd, not unrelated parent directories.
    env_file = (project_root if (project_root / "pyproject.toml").is_file() else Path.cwd()) / ".env"
    load_dotenv(dotenv_path=env_file, override=False, encoding="utf-8")


class LMStudioSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    base_url: str = "http://localhost:1234/v1"
    model: Annotated[str, Field(min_length=1)]
    api_key: SecretStr | None = None
    timeout_seconds: Annotated[float, Field(gt=0, le=600)] = 120
    connect_timeout_seconds: Annotated[float, Field(gt=0, le=60)] = 5
    max_tokens: Annotated[int, Field(ge=128, le=16384)] = 2048
    # Verified against the local LM Studio API; "none" disables thinking for Qwen.
    # Leave unset for backends/models that do not support this field.
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = None
    # Initial non-thinking profile from the Qwen3.8 model card, not a benchmark.
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.7
    top_p: Annotated[float, Field(gt=0, le=1)] = 0.8
    top_k: Annotated[int, Field(ge=1)] = 20
    presence_penalty: Annotated[float, Field(ge=-2, le=2)] = 1.5
    repeat_penalty: Annotated[float, Field(gt=0)] = 1.0
    max_response_bytes: Annotated[int, Field(ge=1024)] = 1_000_000
    max_prompt_chars: Annotated[int, Field(ge=1024)] = 100_000

    @field_validator("base_url")
    @classmethod
    def valid_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("LM_STUDIO_BASE_URL должен быть HTTP(S)-адресом без credentials/query/fragment")
        if parsed.path.rstrip("/") != "/v1":
            raise ValueError("LM_STUDIO_BASE_URL должен оканчиваться на /v1")
        return value.rstrip("/")

    @field_validator("model")
    @classmethod
    def nonblank_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Укажите точный LM_STUDIO_MODEL из LM Studio")
        return value.strip()

    @classmethod
    def from_env(cls) -> "LMStudioSettings":
        values = {}
        for name in cls.model_fields:
            value = os.environ.get("LM_STUDIO_" + name.upper())
            if value is not None:
                values[name] = value
        return cls.model_validate(values)
