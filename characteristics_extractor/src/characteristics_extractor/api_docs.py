"""OpenAPI descriptions and error schemas; no changes to extraction behavior."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .schemas import Issue


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ErrorDetail(BaseModel):
    code: str = Field(description="Машиночитаемый код ошибки, например llm_timeout или invalid_state")
    message: str = Field(description="Описание причины ошибки")
    issues: list[Issue] | None = Field(default=None, description="Причины неполноты справочника при HTTP 409")


class ServiceError(BaseModel):
    detail: ErrorDetail


class ValidationProblem(BaseModel):
    # FastAPI/Pydantic may also provide input, ctx and other diagnostic fields.
    model_config = ConfigDict(extra="allow")
    loc: list[str | int]
    msg: str
    type: str
    input: Any = None


class RequestValidationErrorResponse(BaseModel):
    detail: list[ValidationProblem]


EXTRACT_DESCRIPTION = """
**Первый вызов:** передайте JSON-ответ поиска целиком: `query`, `canonical_query`,
`lemmatized_query`, `candidates`. Поле `attributes` отсутствует или равно `null`.
Сервис загрузит справочник по кодам кандидатов и один раз вызовет LM Studio.
Поле `search_target` в ответе — название искомого товара без характеристик:
например, для «Молоток с рукоятью 15 см» оно равно «Молоток».
Если товар не назван однозначно, `search_target=null`; первый кандидат не подставляется.
Извлекаются явные и неявные свойства с конкретными значениями. Кандидаты не фильтруются.

**Уточнение:** отправьте весь полученный документ на этот же endpoint.
В нужном атрибуте заполните `characteristic_id` из вариантов либо исправьте
`original_value` / `original_value.unit`, поставьте `resolution_source: user`
и очистите `clarifications`. Сохраните `search_target`, `characteristic_options`, исходные запросы,
кандидатов и `input_fingerprint`. Повторный вызов не использует LLM или сессии.
Сервер заново вычислит названия, нормализованные значения и оставшиеся вопросы.
Пустой `attributes: []` означает продолжение без свойств, а не новый разбор.

**HTTP 200** может содержать `status: needs_clarification`: показывайте
`clarifications` и блокирующие `issues`. Неизвестное свойство помечается
`status: unknown` и сообщением «Неизвестная характеристика».
Неравенства, отрицания, диапазоны и альтернативы возвращаются как
`unsupported_constraint`; для них исправьте исходный запрос и начните новый разбор.

Для нового текста/набора кандидатов сбросьте `attributes` и `input_fingerprint`
в `null`, `clarifications` и `issues` в `[]`. Контрольная сумма не является
подписью или токеном авторизации. Межполевые проверки выполняются Python
дополнительно к JSON Schema.
"""

REQUEST_EXAMPLES = {
    "initial": {
        "summary": "Первичный запрос из сервиса поиска",
        "description": "Минимальный пример с одним кандидатом. Можно передать весь список кандидатов.",
        "value": {
            "query": "Молоток рукоять 15 см",
            "canonical_query": "Молоток рукоять 15 см",
            "lemmatized_query": "молоток рукоять 15 см",
            "candidates": [{
                "ktru_code": "25.73.30.141-00000001", "name": "Молоток", "status": "ACTIVE",
                "okpd2_code": "25.73.30.141", "rrf_score": 0.02967032967032967, "is_template": False,
            }],
        },
    },
}

EXTRACT_RESPONSES = {
    200: {"description": "Разбор завершён или требуется пользовательское уточнение; смотрите status, clarifications и issues."},
    409: {"model": ServiceError, "description": "Неполный справочник КТРУ; detail.code=incomplete_catalog, причины в detail.issues."},
    422: {
        "model": ServiceError | RequestValidationErrorResponse,
        "description": "Ошибка структуры входа (detail — массив) или состояния уточнения (detail — объект с code=invalid_state).",
        "content": {"application/json": {"examples": {
            "invalid_state": {"summary": "Изменён контекст уточнения", "value": {"detail": {
                "code": "invalid_state", "message": "Изменился запрос/список кандидатов или отсутствует input_fingerprint. Отправьте attributes=null.",
            }}},
            "validation": {"summary": "Нет обязательного поля", "value": {"detail": [{
                "loc": ["body", "query"], "msg": "Field required", "type": "missing", "input": {},
            }]}},
        }}},
    },
    502: {"model": ServiceError, "description": "Некорректный/обрезанный ответ LLM или превышение лимита: llm_invalid_output, llm_output_truncated, llm_size_limit."},
    503: {"model": ServiceError, "description": "LM Studio или КТРУ недоступны либо модель не настроена: llm_unavailable, catalog_unavailable, configuration_error."},
    504: {"model": ServiceError, "description": "Истёк срок ожидания LM Studio: llm_timeout."},
}
