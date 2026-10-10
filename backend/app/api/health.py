"""Проверка доступности SQLite и основных таблиц каталога."""

import sqlite3
from contextlib import closing

from fastapi import APIRouter, HTTPException, status

from app.db.session import connect
from app.dependencies import SettingsDependency

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: SettingsDependency) -> dict[str, str]:
    try:
        with closing(connect(settings.database_path)) as connection:
            connection.execute("SELECT code FROM ktru_position LIMIT 0")
            connection.execute("SELECT id FROM ktru_characteristic LIMIT 0")
            connection.execute("SELECT id FROM ktru_characteristic_value LIMIT 0")
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных КТРУ недоступна или схема не загружена",
        ) from exc
    return {"status": "ok", "database": "ok"}
