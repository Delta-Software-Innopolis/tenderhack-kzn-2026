"""Wire models for initial search results and client-owned clarification state.

Requests are editable documents, not trusted previous server responses. The
pipeline must resolve IDs against KTRU and recompute derived fields on every
request. These models validate structure, source references and response
invariants; they neither load KTRU nor invoke a model.
"""

from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StringConstraints,
    model_validator,
)

NonEmpty = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
Number = StrictInt | StrictFloat
Status = Literal["completed", "needs_clarification"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class SearchCandidate(ContractModel):
    ktru_code: NonEmpty
    name: NonEmpty
    status: NonEmpty
    okpd2_code: str | None
    rrf_score: Number
    is_template: bool


class SourceSpan(ContractModel):
    """Half-open Python character offsets in the original `query`, not lemmas."""

    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end <= self.start:
            raise ValueError("source_span.end должен быть больше start")
        return self


class OkeiUnit(ContractModel):
    okei_code: NonEmpty
    name: NonEmpty


class OriginalNumber(ContractModel):
    type: Literal["number"]
    value: Number
    unit: NonEmpty | None = None


class OriginalString(ContractModel):
    type: Literal["string"]
    value: NonEmpty
    unit: None = None


class OriginalBoolean(ContractModel):
    type: Literal["boolean"]
    value: bool
    unit: None = None


OriginalValue = Annotated[
    OriginalNumber | OriginalString | OriginalBoolean,
    Field(discriminator="type"),
]


class NormalizedNumber(ContractModel):
    type: Literal["number"]
    value: Number
    unit: OkeiUnit | None = None


class NormalizedString(OriginalString):
    pass


class NormalizedBoolean(OriginalBoolean):
    pass


NormalizedValue = Annotated[
    NormalizedNumber | NormalizedString | NormalizedBoolean,
    Field(discriminator="type"),
]


class Attribute(ContractModel):
    id: NonEmpty
    source_text: NonEmpty = Field(description="Дословный фрагмент исходного query")
    source_span: SourceSpan = Field(description="Позиции [start, end) в символах Python Unicode исходного query")
    mention_type: Literal["explicit", "implicit"] = Field(description="Характеристика названа явно или восстановлена из контекста")
    status: Literal["resolved", "unknown", "needs_clarification"]
    original_value: OriginalValue = Field(description="Исходное значение; при уточнении фронт меняет его или его unit")
    characteristic_id: NonEmpty | None = None
    characteristic_name: NonEmpty | None = None
    normalized_value: NormalizedValue | None = Field(default=None, description="Вычисляется сервером по выбранной характеристике КТРУ")
    extracted_name: NonEmpty | None = None
    message: NonEmpty | None = None
    resolution_source: Literal["model", "user"] = "model"
    # Retained here because the front end may clear the entire questions array.
    characteristic_options: list["CharacteristicOption"] = Field(default_factory=list, description="Варианты выбора. Обязательно сохранять при повторной отправке, даже если clarifications очищен")


class CharacteristicOption(ContractModel):
    """Select by characteristic_id; name is for presentation only."""

    characteristic_id: NonEmpty
    name: NonEmpty
    product_name: str | None = None
    unit_names: list[str] = Field(default_factory=list)


class Clarification(ContractModel):
    id: NonEmpty
    attribute_id: NonEmpty
    kind: Literal["choose_characteristic", "specify_unit", "specify_value"]
    question: NonEmpty
    options: list[CharacteristicOption] = Field(default_factory=list)
    suggested_values: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_options(self) -> Self:
        if self.kind == "choose_characteristic":
            ids = [option.characteristic_id for option in self.options]
            if len(ids) < 2 or len(ids) != len(set(ids)):
                raise ValueError("Для выбора нужны минимум две разные характеристики")
        elif self.options:
            raise ValueError("options используется только для выбора характеристики")
        return self


class Issue(ContractModel):
    id: NonEmpty
    code: Literal[
        "unsupported_constraint",
        "candidate_not_found",
        "incomplete_catalog",
        "incompatible_unit",
        "unmapped_value",
        "invalid_selection",
    ]
    message: NonEmpty
    blocking: bool
    attribute_id: NonEmpty | None = None
    candidate_code: NonEmpty | None = None
    source_text: NonEmpty | None = None
    source_span: SourceSpan | None = None

    @model_validator(mode="after")
    def paired_source(self) -> Self:
        if (self.source_text is None) != (self.source_span is None):
            raise ValueError("source_text и source_span у диагностики задаются вместе")
        return self


class ExtractionDocument(ContractModel):
    """Shared extraction state, without the input-only candidate list."""
    schema_version: Literal["1.0"] = "1.0"
    search_target: NonEmpty | None = Field(default=None, description="Цель поиска: краткое название товара, например Молоток. Извлекается при первом вызове; возвращать при уточнениях. null — товар не указан однозначно")
    query: NonEmpty = Field(description="Исходный запрос пользователя; источник смысла и координат цитат")
    canonical_query: NonEmpty = Field(description="Канонический запрос из сервиса поиска")
    lemmatized_query: NonEmpty = Field(description="Лемматизированный запрос из сервиса поиска")
    attributes: list[Attribute] | None = Field(default=None, description="Отсутствует/null — первичное извлечение с LLM; массив, включая [], — продолжение без LLM")
    clarifications: list[Clarification] = Field(default_factory=list, description="Фронт может очистить вопросы; сервер восстановит неотвеченные")
    issues: list[Issue] = Field(default_factory=list, description="Диагностика; сохранять при уточнении, очистить при новом разборе")
    # Client can return a previous status. The pipeline must recompute it.
    status: Literal["pending", "completed", "needs_clarification"] = "pending"
    # Detects accidental context changes; not a signature or an authorization token.
    input_fingerprint: NonEmpty | None = Field(default=None, description="Возвращать неизменённым при уточнениях; защита от случайной смены контекста, не подпись")

    @model_validator(mode="after")
    def consistent_references(self) -> Self:
        attributes = self.attributes or []
        for label, items in (
            ("attributes", attributes),
            ("clarifications", self.clarifications),
            ("issues", self.issues),
        ):
            ids = [item.id for item in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f"Повторяющиеся id в {label}")

        attribute_ids = {attribute.id for attribute in attributes}
        for item in [*self.clarifications, *self.issues]:
            if item.attribute_id is not None and item.attribute_id not in attribute_ids:
                raise ValueError("attribute_id не ссылается на существующий атрибут")
        for item in [*attributes, *self.issues]:
            span = item.source_span
            if span is not None and (span.end > len(self.query) or self.query[span.start:span.end] != item.source_text):
                raise ValueError("source_text и source_span должны соответствовать query")
        return self


class ExtractRequest(ExtractionDocument):
    candidates: list[SearchCandidate] = Field(description="Все кандидаты из поиска. Обязательны при каждом вызове, включая уточнения; в ответе не возвращаются")

    @property
    def is_initial(self) -> bool:
        return self.attributes is None


class ExtractResponse(ExtractionDocument):
    """Validated server result; stricter than the client-editable request."""

    attributes: list[Attribute] = Field(description="Извлечённые характеристики, включая неизвестные и требующие уточнения")
    search_target: NonEmpty | None = Field(description="Название искомого товара без характеристик, например Молоток. null — цель не определена однозначно")
    status: Status = Field(description="completed — нет вопросов/блокирующих issues; needs_clarification — нужен ввод пользователя")

    @model_validator(mode="after")
    def consistent_result(self) -> Self:
        pending_ids = set()
        for attribute in self.attributes:
            if attribute.status == "resolved":
                if (
                    attribute.characteristic_id is None
                    or attribute.characteristic_name is None
                    or attribute.normalized_value is None
                ):
                    raise ValueError("resolved требует характеристику и нормализованное значение")
            elif attribute.status == "unknown":
                if (
                    attribute.characteristic_id is not None
                    or attribute.characteristic_name is not None
                    or attribute.normalized_value is not None
                    or attribute.extracted_name is None
                    or attribute.message != "Неизвестная характеристика"
                ):
                    raise ValueError("unknown требует исходное имя и сообщение без привязки к КТРУ")
            else:
                pending_ids.add(attribute.id)
                if attribute.normalized_value is not None:
                    raise ValueError("Неуточнённый атрибут не имеет окончательного значения")

        question_ids = {item.attribute_id for item in self.clarifications}
        if question_ids != pending_ids:
            raise ValueError("Вопросы должны соответствовать всем неуточнённым атрибутам")

        needs_input = bool(pending_ids) or any(issue.blocking for issue in self.issues)
        expected_status = "needs_clarification" if needs_input else "completed"
        if self.status != expected_status:
            raise ValueError(f"Ожидается status={expected_status}")
        return self
