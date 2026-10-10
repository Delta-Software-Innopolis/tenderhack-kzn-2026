"""Зависимости FastAPI: соединения SQLite; сервисы будут добавлены позже."""

from collections.abc import Iterator
from contextlib import closing
from sqlite3 import Connection
from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.db.session import connect

SettingsDependency = Annotated[Settings, Depends(get_settings)]


def get_db(settings: SettingsDependency) -> Iterator[Connection]:
    with closing(connect(settings.database_path)) as connection:
        yield connection


DatabaseDependency = Annotated[Connection, Depends(get_db)]
