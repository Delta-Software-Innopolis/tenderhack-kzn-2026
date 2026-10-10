"""Соединения SQLite; закрытие соединения выполняет вызывающий код."""

import sqlite3
from pathlib import Path


def connect(database_path: Path, *, read_only: bool = True) -> sqlite3.Connection:
    # mode=ro не создаёт пустую БД при ошибочном пути в настройках API.
    mode = "ro" if read_only else "rwc"
    connection = sqlite3.connect(
        f"{database_path.resolve().as_uri()}?mode={mode}",
        uri=True,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
