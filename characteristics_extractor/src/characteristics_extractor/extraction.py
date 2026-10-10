"""LLM extraction stage; normalization and continuation live in pipeline.py."""

from hashlib import sha256
import json
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from .catalog import CatalogContext
from .llm import LLMInvalidOutputError, LMStudioClient
from .prompts import build_messages
from .schemas import (
    CharacteristicOption, ContractModel, ExtractRequest, Issue, NonEmpty,
    OriginalValue, SearchCandidate, SourceSpan,
)


class ModelFact(ContractModel):
    source_text: NonEmpty
    occurrence: Annotated[int, Field(ge=0)] = 0
    mention_type: Literal["explicit", "implicit"]
    extracted_name: NonEmpty
    original_value: OriginalValue
    characteristic_ids: Annotated[list[NonEmpty], Field(max_length=8)]


class ModelUnsupported(ContractModel):
    source_text: NonEmpty
    occurrence: Annotated[int, Field(ge=0)] = 0
    reason: Literal["inequality", "negation", "range", "alternatives"]


class ModelExtraction(ContractModel):
    search_target: NonEmpty | None = Field(description="Краткое название искомого товара из query без значений характеристик; null, если товар не указан однозначно")
    facts: Annotated[list[ModelFact], Field(max_length=32)]
    unsupported: Annotated[list[ModelUnsupported], Field(max_length=32)]


class ExtractedFact(ContractModel):
    id: NonEmpty
    source_text: NonEmpty
    source_span: SourceSpan
    mention_type: Literal["explicit", "implicit"]
    extracted_name: NonEmpty
    original_value: OriginalValue
    mapping_status: Literal["matched", "unknown", "ambiguous"]
    characteristic_options: list[CharacteristicOption]
    message: str | None = None


class InitialExtraction(ContractModel):
    """Intermediate service result, intentionally distinct from ExtractResponse."""

    stage: Literal["initial_extraction"] = "initial_extraction"
    search_target: NonEmpty | None
    query: str
    canonical_query: str
    lemmatized_query: str
    candidates: list[SearchCandidate]
    facts: list[ExtractedFact]
    issues: list[Issue]


class ExtractionInputError(ValueError):
    pass


class IncompleteCatalogError(ExtractionInputError):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("Контекст КТРУ неполон; нельзя достоверно определять неизвестные характеристики")


def _strict_schema(node):
    """Require even nullable fields explicitly; keep schema and parser in agreement."""
    if isinstance(node, list):
        return [_strict_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    result = {key: _strict_schema(value) for key, value in node.items() if key not in {"default", "title"}}
    if result.get("type") == "object":
        result["additionalProperties"] = False
        result["required"] = list(result.get("properties", {}))
    return result


def prepare_extraction(request: ExtractRequest, catalog: CatalogContext) -> tuple[list[dict], dict, dict[str, str]]:
    if not request.is_initial:
        raise ExtractionInputError("Первичное извлечение допустимо только при attributes=null")
    if request.candidates != catalog.candidates:
        raise ExtractionInputError("Контекст собран для другого списка кандидатов")
    if not catalog.complete or not catalog.definitions:
        raise IncompleteCatalogError(catalog.issues)
    # Short aliases avoid making the model copy 64-character hashes. These are
    # request-local; only authoritative stable IDs leave this extraction layer.
    aliases = {f"c{index}": definition.id for index, definition in enumerate(catalog.definitions, 1)}
    reverse = {stable: alias for alias, stable in aliases.items()}
    prompt_catalog = catalog.to_prompt_context()
    for product in prompt_catalog["products"]:
        for characteristic in product["characteristics"]:
            characteristic["id"] = reverse[characteristic["id"]]
    schema = _strict_schema(ModelExtraction.model_json_schema())
    schema["$defs"]["ModelFact"]["properties"]["characteristic_ids"]["items"] = {
        "type": "string", "enum": list(aliases),
    }
    messages = build_messages(request.query, request.canonical_query, request.lemmatized_query, prompt_catalog)
    return messages, schema, aliases


def _span(query: str, text: str, occurrence: int) -> SourceSpan:
    offset = 0
    for _ in range(occurrence + 1):
        start = query.find(text, offset)
        if start < 0:
            raise LLMInvalidOutputError("Модель указала фрагмент, которого нет в исходном query")
        offset = start + len(text)
    return SourceSpan(start=start, end=offset)


def _stable_id(prefix: str, data: list) -> str:
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return prefix + "_" + sha256(encoded.encode()).hexdigest()


def bind_extraction(raw: dict, request: ExtractRequest, catalog: CatalogContext, aliases: dict[str, str]) -> InitialExtraction:
    try:
        extracted = ModelExtraction.model_validate(raw)
    except ValidationError as error:
        raise LLMInvalidOutputError("Ответ модели не соответствует схеме извлечения") from error

    facts = []
    identities = set()
    for fact in extracted.facts:
        span = _span(request.query, fact.source_text, fact.occurrence)
        if len(fact.characteristic_ids) != len(set(fact.characteristic_ids)):
            raise LLMInvalidOutputError("Модель повторила вариант характеристики")
        options = []
        for alias in fact.characteristic_ids:
            stable_id = aliases.get(alias)
            definition = catalog.get_definition(stable_id) if stable_id else None
            if definition is None:
                raise LLMInvalidOutputError("Модель выбрала характеристику вне переданного справочника")
            options.append(CharacteristicOption(characteristic_id=definition.id, name=definition.name))
        options.sort(key=lambda option: option.characteristic_id)
        identity = [span.start, span.end, [option.characteristic_id for option in options]]
        if not options:
            identity.append(" ".join(fact.extracted_name.casefold().split()))
        fact_id = _stable_id("fact", [request.query, *identity])
        if fact_id in identities:
            raise LLMInvalidOutputError("Модель повторила один и тот же факт")
        identities.add(fact_id)
        status = "unknown" if not options else "matched" if len(options) == 1 else "ambiguous"
        facts.append(ExtractedFact(
            id=fact_id, source_text=fact.source_text, source_span=span,
            mention_type=fact.mention_type, extracted_name=fact.extracted_name,
            original_value=fact.original_value, mapping_status=status,
            characteristic_options=options,
            message="Неизвестная характеристика" if status == "unknown" else None,
        ))

    labels = {"inequality": "неравенство", "negation": "отрицание", "range": "диапазон", "alternatives": "альтернативы"}
    issues = []
    seen_issues = set()
    for unsupported in extracted.unsupported:
        span = _span(request.query, unsupported.source_text, unsupported.occurrence)
        for fact in facts:
            if max(span.start, fact.source_span.start) < min(span.end, fact.source_span.end):
                raise LLMInvalidOutputError("Неподдерживаемое ограничение одновременно выдано как равенство")
        issue_id = _stable_id("issue", [request.query, span.start, span.end, unsupported.reason])
        if issue_id in seen_issues:
            raise LLMInvalidOutputError("Модель повторила неподдерживаемое ограничение")
        seen_issues.add(issue_id)
        issues.append(Issue(
            id=issue_id, code="unsupported_constraint", blocking=True,
            message=f"Укажите конкретное значение: {labels[unsupported.reason]} не поддерживается.",
            source_text=unsupported.source_text, source_span=span,
        ))
    facts.sort(key=lambda fact: (fact.source_span.start, fact.source_span.end, fact.id))
    issues.sort(key=lambda issue: (issue.source_span.start, issue.id))
    return InitialExtraction(
        search_target=extracted.search_target.strip() if extracted.search_target is not None else None,
        query=request.query, canonical_query=request.canonical_query,
        lemmatized_query=request.lemmatized_query,
        candidates=[candidate.model_copy(deep=True) for candidate in request.candidates],
        facts=facts, issues=issues,
    )


async def extract_initial(request: ExtractRequest, catalog: CatalogContext, client: LMStudioClient) -> InitialExtraction:
    messages, schema, aliases = prepare_extraction(request, catalog)
    raw = await client.complete(messages, schema)
    return bind_extraction(raw, request, catalog, aliases)
