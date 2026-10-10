import json
import sqlite3
import xml.etree.ElementTree as ET
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi import Path as PathParameter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Разрешённые origins фронтенда: схема, хост и порт, без пути и завершающего слеша.
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]

app = FastAPI(
    title="API каталога КТРУ",
    version="0.1.0",
    description=(
        "Получение карточек товаров по полному коду КТРУ и просмотр каталога "
        "с пагинацией и фильтрацией по категориям хакатона. "
        "Карточки включают рубрики, характеристики, допустимые значения и единицы измерения. "
        "Неизвестные значения полей возвращаются как null. "
        "Ошибки параметров запроса возвращаются с HTTP 422."
    ),
    openapi_tags=[
        {"name": "Каталог", "description": "Позиции КТРУ и их характеристики."},
        {"name": "Сервис", "description": "Служебные эндпоинты."},
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


class Rubric(BaseModel):
    """Рубрика справочника КТРУ; отличается от категории хакатона."""

    code: str | None = Field(description="Код рубрики", examples=["128"])
    name: str | None = Field(description="Название рубрики", examples=["Мебель"])


class CharacteristicValue(BaseModel):
    """Текстовое значение, числовой диапазон или конкретное число из КТРУ."""

    value_code: str | None = Field(description="Код допустимого значения")
    quality_description: str | None = Field(description="Текстовое значение", examples=["Круглый"])
    okei_code: str | None = Field(description="Код единицы измерения по ОКЕИ", examples=["003"])
    okei_name: str | None = Field(description="Название единицы измерения", examples=["Миллиметр"])
    min_value: float | None = Field(description="Нижняя граница диапазона", examples=[100.0])
    min_notation: str | None = Field(
        description="Условие нижней границы: greater (>) или greaterOrEqual (>=)",
        examples=["greaterOrEqual"],
    )
    max_value: float | None = Field(description="Верхняя граница диапазона", examples=[150.0])
    max_notation: str | None = Field(
        description="Условие верхней границы: less (<) или lessOrEqual (<=)",
        examples=["less"],
    )
    concrete_value: float | None = Field(description="Конкретное числовое значение")


class Characteristic(BaseModel):
    """Характеристика товара и все её допустимые значения."""

    id: int = Field(description="Внутренний идентификатор характеристики в базе")
    code: str | None = Field(description="Код характеристики КТРУ")
    name: str | None = Field(description="Название характеристики", examples=["Длина рукоятки"])
    type: int | None = Field(description="Тип: 1 — качественная, 2 — количественная")
    is_required: int | None = Field(description="Обязательность: 1 — обязательная, 0 — необязательная")
    values: list[CharacteristicValue] = Field(description="Допустимые значения; пустой массив, если их нет")


class Item(BaseModel):
    """Полная карточка позиции КТРУ без служебных полей поискового индекса."""

    code: str = Field(description="Полный код КТРУ", examples=["25.73.30.141-00000012"])
    version: int = Field(description="Номер версии позиции", examples=[2])
    version_code: str | None = Field(description="Код версии позиции")
    name: str | None = Field(description="Наименование товара", examples=["Молоток"])
    okpd2_code: str | None = Field(description="Код ОКПД2", examples=["25.73.30.141"])
    okpd2_name: str | None = Field(description="Наименование по ОКПД2", examples=["Молотки"])
    status: str | None = Field(description="Статус позиции: ACTIVE, INACTIVE или TERMINATED", examples=["ACTIVE"])
    is_template: int = Field(description="Признак шаблона: 1 — шаблон, 0 — обычная позиция")
    publish_date: str | None = Field(description="Дата публикации в исходном формате КТРУ", examples=["2026-06-03T13:07:16+03:00"])
    update_date: str | None = Field(description="Дата обновления в исходном формате КТРУ")
    date_start: str | None = Field(description="Дата начала применения в исходном формате КТРУ")
    date_end: str | None = Field(description="Дата окончания применения в исходном формате КТРУ")
    rubrics: list[Rubric] = Field(description="Рубрики КТРУ; пустой массив, если их нет")
    characteristics: list[Characteristic] = Field(description="Характеристики товара; пустой массив, если их нет")


class ErrorResponse(BaseModel):
    detail: str = Field(description="Описание ошибки")


class ItemsCountResponse(BaseModel):
    count: int = Field(ge=0, description="Количество товаров с учётом фильтра категории", examples=[2763])


class RootResponse(BaseModel):
    message: str = Field(description="Приветственное сообщение", examples=["Hello World"])


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


def category_filter(category: str | None) -> tuple[str, list[str]]:
    """Общий фильтр категории для списка товаров и подсчёта их количества."""
    if category is None:
        return "", []
    # JSON-массив занимает один SQL-параметр независимо от размера категории.
    return "WHERE p.code IN (SELECT value FROM json_each(?))", [category_codes(category)]


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


@app.get(
    "/",
    response_model=RootResponse,
    tags=["Сервис"],
    summary="Приветствие сервера",
    operation_id="getRoot",
)
async def root():
    return {"message": "Hello World"}


@app.get(
    "/item/{item_id}",
    response_model=Item,
    tags=["Каталог"],
    summary="Получить товар по коду КТРУ",
    operation_id="getItem",
    response_description="Полная карточка найденного товара",
    responses={
        404: {
            "model": ErrorResponse,
            "description": "Товар с указанным кодом КТРУ отсутствует в базе",
            "content": {"application/json": {"example": {"detail": "Товар не найден"}}},
        },
    },
)
def get_item(
    item_id: str = PathParameter(
        description="Полный код КТРУ с точками и дефисом. Поиск по точному совпадению.",
        examples=["25.73.30.141-00000012"],
    ),
):
    """Возвращает товар вместе с рубриками, характеристиками и допустимыми значениями.

    Поиск охватывает все статусы позиций. Если код отсутствует, возвращается HTTP 404.
    """
    with closing(connect_db()) as conn:
        row = conn.execute(
            f"SELECT {POSITION_FIELDS} FROM ktru_position p WHERE p.code = ?",
            (item_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Товар не найден")
        return serialize_items(conn, [row])[0]


@app.get("/items", response_model=list[Item], include_in_schema=False)
@app.get(
    "/items/",
    response_model=list[Item],
    tags=["Каталог"],
    summary="Получить список товаров",
    operation_id="listItems",
    response_description="Массив полных карточек товаров; пустой массив, если страница пуста",
    responses={
        503: {
            "model": ErrorResponse,
            "description": "Исходные XML выбранной категории отсутствуют на сервере",
            "content": {"application/json": {"example": {"detail": "Исходные данные категории недоступны"}}},
        },
    },
)
def get_items(
    offset: int = Query(
        default=0, ge=0, le=SQLITE_MAX_INTEGER,
        description="Сколько товаров пропустить после фильтрации по категории", examples=[0, 20],
    ),
    limit: int = Query(
        default=20, ge=1, le=SQLITE_MAX_INTEGER,
        description="Максимальное количество товаров в ответе", examples=[20],
    ),
    category: Literal["мебель", "одежда", "инструменты"] | None = Query(
        default=None,
        description="Категория хакатона. Не передавайте параметр для просмотра всего каталога.",
        examples=["мебель"],
    ),
):
    """Список полных карточек, отсортированных по коду КТРУ.

    Без category выборка включает все позиции базы, в том числе неактивные.
    offset и limit применяются после фильтрации по категории хакатона.
    Категория определяется по исходной XML-выгрузке, а не по рубрике КТРУ.
    Если offset выходит за пределы выборки, возвращается пустой массив с HTTP 200.
    Также поддерживается путь /items без завершающего слеша.
    """
    where, parameters = category_filter(category)

    with closing(connect_db()) as conn:
        rows = conn.execute(
            f"""SELECT {POSITION_FIELDS} FROM ktru_position p
                {where} ORDER BY p.code LIMIT ? OFFSET ?""",
            [*parameters, limit, offset],
        ).fetchall()
        return serialize_items(conn, rows)


@app.get("/items/count/", response_model=ItemsCountResponse, include_in_schema=False)
@app.get(
    "/items/count",
    response_model=ItemsCountResponse,
    tags=["Каталог"],
    summary="Получить количество товаров",
    operation_id="countItems",
    response_description="Количество товаров в базе с учётом выбранной категории",
    responses={
        503: {
            "model": ErrorResponse,
            "description": "Исходные XML выбранной категории отсутствуют на сервере",
            "content": {"application/json": {"example": {"detail": "Исходные данные категории недоступны"}}},
        },
    },
)
def count_items(
    category: Literal["мебель", "одежда", "инструменты"] | None = Query(
        default=None,
        description="Категория хакатона. Не передавайте параметр для подсчёта всего каталога.",
        examples=["мебель"],
    ),
):
    """Считает позиции КТРУ в базе, включая неактивные, без загрузки карточек.

    Фильтр категории совпадает с фильтром GET /items/; пагинация не применяется.
    Если подходящих товаров нет, возвращается {"count": 0} с HTTP 200.
    """
    where, parameters = category_filter(category)
    with closing(connect_db()) as conn:
        count = conn.execute(
            f"SELECT COUNT(*) FROM ktru_position p {where}", parameters,
        ).fetchone()[0]
        return {"count": count}
