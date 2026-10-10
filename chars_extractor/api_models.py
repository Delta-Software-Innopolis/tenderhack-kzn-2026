"""Public HTTP request/response schemas for the extraction service."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


CandidateCode = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{
        "normalized_query": "молоток длина ручка 15 сантиметр",
        "candidate_codes": ["25.73.30.141-00000012"],
    }]})

    normalized_query: str = Field(description="Запрос в начальной форме, с сохранёнными единицами, диапазонами и отрицаниями")
    candidate_codes: list[CandidateCode] = Field(description="Коды уже выбранных кандидатов КТРУ; пустой список допустим")


class SearchCandidate(BaseModel):
    """Only the candidate code is needed; search metadata is accepted and ignored."""

    ktru_code: CandidateCode = Field(description="Код кандидата КТРУ")
    name: str | None = Field(default=None, description="Название из поиска; карточка читается из базы")
    status: str | None = Field(default=None, description="Статус позиции из поиска")
    okpd2_code: str | None = Field(default=None, description="Код ОКПД2 из поиска")
    rrf_score: float | None = Field(default=None, description="Оценка поиска; не влияет на сопоставление характеристик")


class SearchResponseRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "query": "Сапог", "canonical_query": "Сапог", "lemmatized_query": "сапог",
        "candidates": [{"ktru_code": "15.20.11.113-00000015", "name": "Сапоги резиновые формовые",
                        "status": "ACTIVE", "okpd2_code": "15.20.11.113", "rrf_score": 0.01639344262295082}],
    }]})

    query: str | None = Field(default=None, description="Исходный запрос; не используется вместо нормализованного")
    canonical_query: str | None = Field(default=None, description="Канонический запрос сервиса поиска")
    lemmatized_query: str = Field(description="Нормализованный запрос, который будет передан экстрактору")
    candidates: list[SearchCandidate] = Field(description="Готовая выборка поиска; её порядок сохраняется")


class Interval(BaseModel):
    min: int | float | None = Field(description="Нижняя граница; null означает отсутствие границы")
    max: int | float | None = Field(description="Верхняя граница; null означает отсутствие границы")
    min_inclusive: bool = Field(description="Включена ли нижняя граница")
    max_inclusive: bool = Field(description="Включена ли верхняя граница")


class ValueBase(BaseModel):
    name: str = Field(description="Название характеристики запроса или КТРУ")
    unit: str | None = Field(description="Единица измерения; null для строк или при отсутствии единицы")
    value_code: str | None = Field(default=None, description="Код допустимого значения КТРУ, только для значений каталога")
    value_codes: list[str | None] | None = Field(default=None, description="Исходные коды одинакового значения при объединении дубликатов")
    source: str | None = Field(default=None, description="Исходный фрагмент нормализованного запроса")
    start: int | None = Field(default=None, description="Начало фрагмента в нормализованной строке, от нуля")
    end: int | None = Field(default=None, description="Конец фрагмента, не включён")
    negated: bool = Field(default=False, description="Значение исключено пользователем")
    possible_names: list[str] | None = Field(default=None, description="Возможные названия для неоднозначного свойства")


class StringValue(ValueBase):
    type: Literal["string"]
    value: str = Field(description="Строковое значение", examples=["резина"])


class NumberValue(ValueBase):
    type: Literal["number"]
    value: int | float = Field(description="Числовое значение", examples=[15])


class IntervalValue(ValueBase):
    type: Literal["interval"]
    value: Interval


TypedValue = Annotated[StringValue | NumberValue | IntervalValue, Field(discriminator="type")]


class CatalogIssue(BaseModel):
    value_id: int = Field(description="Идентификатор некорректного значения в базе")
    reason: str = Field(description="Описание проблемы")


class CatalogCharacteristic(BaseModel):
    id: int = Field(description="Идентификатор характеристики в базе")
    code: str | None = Field(description="Код характеристики КТРУ")
    name: str = Field(description="Официальное название характеристики")
    ktru_type: int | None = Field(description="Исходный тип КТРУ; отличается от string/number/interval")
    kind: int | None = Field(description="Вид характеристики из КТРУ")
    is_required: int | None = Field(description="Признак обязательности характеристики в КТРУ; null при расхождении дубликатов")
    choice_type: int | None = Field(description="Тип выбора значений в КТРУ")
    values: list[TypedValue] = Field(description="Унифицированные допустимые значения")
    issues: list[CatalogIssue] = Field(description="Ошибки исходных данных")
    source_ids: list[int] | None = Field(default=None, description="Идентификаторы объединённых строк одной характеристики внутри товара")


class CatalogReference(BaseModel):
    candidate_code: str
    characteristic_id: int
    code: str | None
    name: str


class QueryCharacteristic(CatalogCharacteristic):
    id: None = Field(description="У требования пользователя нет собственной строки в базе")
    is_required: int | None = Field(description="Признак КТРУ, если он одинаков у найденных определений")
    mapping_status: Literal['mapped', 'alternatives', 'not_found', 'ambiguous', 'unit_mismatch']
    match_mode: Literal['single', 'any'] = Field(description="single — конкретное свойство; any — неявное значение допустимо в любом из полей ktru_refs")
    in_ktru: bool = Field(description="Найдено ли название в характеристиках переданных кандидатов; не проверка всего КТРУ")
    reason: str | None
    source: str
    start: int
    end: int
    negated: bool
    unit_inferred: bool
    ktru_refs: list[CatalogReference] = Field(description="Ссылки на реальные характеристики кандидатов")


class CharacteristicMatch(BaseModel):
    query_index: int = Field(description="Индекс характеристики в массиве chars")
    method: Literal["name", "short_name", "value_context", "semantic"] = Field(description="Способ сопоставления названия")
    status: Literal["matched", "value_mismatch", "unit_mismatch", "partial_match", "not_found", "ambiguous", "not_comparable"] = Field(description="Результат сопоставления характеристики")
    characteristic_id: int | None = Field(default=None, description="Однозначно выбранная характеристика КТРУ")
    characteristic_ids: list[int] | None = Field(default=None, description="Исходные строки объединённого свойства или альтернативные характеристики")
    matched_characteristic_ids: list[int] | None = Field(default=None, description="Строки КТРУ, подтвердившие значение при match_mode=any")
    match_mode: Literal['any'] | None = Field(default=None, description="Достаточно совпадения хотя бы с одной альтернативной характеристикой")
    name: str | None = Field(default=None, description="Название выбранной характеристики КТРУ")
    reason: str | None = Field(default=None, description="Причина несовпадения или неопределённости")
    comparison_unit: str | None = Field(default=None, description="Единица запроса, использованная для сравнения с учётом пересчёта")
    unit_inferred: bool | None = Field(default=None, description="Единица унаследована из КТРУ, поскольку отсутствовала в запросе")


class CandidateResult(BaseModel):
    code: str = Field(description="Код рассмотренного кандидата КТРУ")
    name: str = Field(description="Название позиции из базы")
    characteristics: list[CatalogCharacteristic]
    matches: list[CharacteristicMatch]
    status: Literal["matched", "mismatch", "partial_match", "undetermined", "no_constraints"] = Field(description="Итог проверки требований; не статус ACTIVE/INACTIVE позиции КТРУ")


class RejectedCandidate(BaseModel):
    code: str
    name: str
    matches: list[CharacteristicMatch]
    status: Literal['mismatch', 'undetermined']


class UnrecognizedFragment(BaseModel):
    source: str
    start: int
    end: int
    reason: str


class ExtractResponse(BaseModel):
    query: str = Field(description="Нормализованный запрос, переданный экстрактору")
    chars: list[QueryCharacteristic] = Field(description="Только требования пользователя, в структуре характеристик КТРУ; values содержат запрошенные значения в единицах каталога")
    candidates: list[CandidateResult] = Field(description="Кандидаты без противоречий и хотя бы с одним совпадением; при запросе без ограничений — вся входная выборка")
    rejected_candidates: list[RejectedCandidate] = Field(description="Исключённые кандидаты: противоречия требованиям либо отсутствие подтверждённых совпадений")
    unknown_candidate_codes: list[str] = Field(description="Переданные коды, отсутствующие в базе")
    unrecognized: list[UnrecognizedFragment] = Field(description="Неразобранные фрагменты и ошибки разбора")


class ServiceError(BaseModel):
    detail: str = Field(description="Описание ошибки сервиса")


class HealthResponse(BaseModel):
    status: Literal["ok"] = Field(description="HTTP-сервис работает; доступность базы проверяется при обработке запроса")
