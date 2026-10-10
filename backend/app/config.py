"""Настройки из переменных окружения без дополнительных зависимостей."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    app_name: str
    database_path: Path


@lru_cache
def get_settings() -> Settings:
    database_path = Path(os.environ.get("DATABASE_PATH", str(PROJECT_ROOT / "ktru.db")))
    
    return Settings(
        app_name=os.environ.get("APP_NAME", "TenderHack KTRU API"),
        database_path=database_path.expanduser().resolve(),
    )
