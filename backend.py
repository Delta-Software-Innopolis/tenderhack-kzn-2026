import json
import sqlite3
import xml.etree.ElementTree as ET
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query

app = FastAPI()
DB_PATH = Path(__file__).with_name("ktru.db")
RAW_DATA_PATH = Path(__file__).with_name("raw_data")
CATEGORY_DIRECTORIES = {
    "мебель": "furniture",
    "одежда": "clothes",
    "инструменты": "instruments",
}
SQLITE_MAX_INTEGER = 2**63 - 1

# Поля полнотекстового индекса нужны поиску, но не клиенту каталога.
POSITION_FIELDS = """
    p.code, p.version, p.version_code, p.name, p.okpd2_code, p.okpd2_name,
    p.status, p.is_template, p.publish_date, p.update_date, p.date_start, p.date_end
"""


def connect_db() -> sqlite3.Connection:
    """Открыть существующий каталог только для чтения, независимо от cwd."""
    conn = sqlite3.connect(DB_PATH.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@lru_cache(maxsize=3)
def category_codes(category: str) -> str:
    """Коды категории из исходной выгрузки; кеш действует до перезапуска API.

    Рубрики КТРУ не совпадают с категориями хакатона. Например, медицинская
    мебель находится в рубрике «Медицинские изделия», но в папке furniture.
    """
    directory = RAW_DATA_PATH / CATEGORY_DIRECTORIES[category]
    files = sorted(path for path in directory.glob("*.xml") if not path.name.startswith("."))
    if not files:
        raise HTTPException(status_code=503, detail="Исходные данные категории недоступны")

    codes = set()
    for path in files:
        for _, element in ET.iterparse(path, events=("end",)):
            if element.tag.rsplit("}", 1)[-1] == "position":
                code = element.findtext("{*}data/{*}code")
                if code:
                    codes.add(code.strip())
                element.clear()
    return json.dumps(sorted(codes))


def serialize_items(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[dict]:
    """Добавить рубрики и характеристики пакетно, без запросов на каждый товар."""
    items = [dict(row, rubrics=[], characteristics=[]) for row in rows]
    by_code = {item["code"]: item for item in items}
    codes = list(by_code)

    # Ограничиваем число SQL-параметров даже для больших страниц каталога.
    for start in range(0, len(codes), 500):
        batch = codes[start:start + 500]
        placeholders = ",".join("?" for _ in batch)
        for row in conn.execute(
            f"""SELECT position_code, code, name FROM ktru_rubric
                WHERE position_code IN ({placeholders})
                ORDER BY position_code, code, name""",
            batch,
        ):
            by_code[row["position_code"]]["rubrics"].append(
                {"code": row["code"], "name": row["name"]}
            )

        characteristics = {}
        for row in conn.execute(
            f"""SELECT id, position_code, code, name, type, is_required
                FROM ktru_characteristic
                WHERE position_code IN ({placeholders}) ORDER BY id""",
            batch,
        ):
            characteristic = dict(row)
            position_code = characteristic.pop("position_code")
            characteristic["values"] = []
            characteristics[row["id"]] = characteristic
            by_code[position_code]["characteristics"].append(characteristic)

        for row in conn.execute(
            f"""SELECT v.* FROM ktru_char_value v
                JOIN ktru_characteristic c ON c.id = v.characteristic_id
                WHERE c.position_code IN ({placeholders})
                ORDER BY c.id, v.rowid""",
            batch,
        ):
            value = dict(row)
            characteristic_id = value.pop("characteristic_id")
            characteristics[characteristic_id]["values"].append(value)

    return items


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/item/{item_id}")
def get_item(item_id: str):
    """Получить позицию по полному коду КТРУ, например 31.01.10.000-00000001."""
    with closing(connect_db()) as conn:
        row = conn.execute(
            f"SELECT {POSITION_FIELDS} FROM ktru_position p WHERE p.code = ?",
            (item_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Товар не найден")
        return serialize_items(conn, [row])[0]


@app.get("/items", include_in_schema=False)
@app.get("/items/")
def get_items(
    offset: int = Query(default=0, ge=0, le=SQLITE_MAX_INTEGER),
    limit: int = Query(default=20, ge=1, le=SQLITE_MAX_INTEGER),
    category: Literal["мебель", "одежда", "инструменты"] | None = Query(default=None),
):
    """Список полных карточек, отсортированных по коду КТРУ.

    Без category выборка включает все позиции базы, в том числе неактивные.
    offset и limit применяются после фильтрации по категории хакатона.
    """
    where = ""
    parameters = []
    if category is not None:
        # JSON-массив занимает один SQL-параметр независимо от размера категории.
        where = "WHERE p.code IN (SELECT value FROM json_each(?))"
        parameters.append(category_codes(category))
    parameters.extend((limit, offset))

    with closing(connect_db()) as conn:
        rows = conn.execute(
            f"""SELECT {POSITION_FIELDS} FROM ktru_position p
                {where} ORDER BY p.code LIMIT ? OFFSET ?""",
            parameters,
        ).fetchall()
        return serialize_items(conn, rows)
