"""Stateless orchestration: initial LLM extraction or deterministic continuation."""

import asyncio
from hashlib import sha256
import json

from .catalog import CatalogContext, CharacteristicDefinition, prepare_catalog
from .config import LMStudioSettings
from .debug import debug_print
from .extraction import IncompleteCatalogError, extract_initial
from .llm import LMStudioClient
from .normalization import NormalizationProblem, normalize_value, text_key
from .repository import KtruRepository
from .schemas import Attribute, CharacteristicOption, Clarification, ExtractRequest, ExtractResponse, Issue


class RequestStateError(ValueError):
    pass


def input_fingerprint(request: ExtractRequest) -> str:
    data = [request.query, request.canonical_query, request.lemmatized_query,
            sorted({candidate.ktru_code for candidate in request.candidates})]
    return sha256(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def option_for(definition: CharacteristicDefinition) -> CharacteristicOption:
    return CharacteristicOption(
        characteristic_id=definition.id, name=definition.name,
        product_name=definition.product_name,
        unit_names=sorted({unit.name for unit in definition.units if unit and unit.name}),
    )


def _canonical_options(attribute: Attribute, catalog: CatalogContext) -> list[CharacteristicOption]:
    ids = [option.characteristic_id for option in attribute.characteristic_options]
    if len(ids) != len(set(ids)):
        raise RequestStateError("Варианты характеристики не должны повторяться")
    options = []
    for identifier in ids:
        definition = catalog.get_definition(identifier)
        if definition is None:
            raise RequestStateError("Вариант характеристики отсутствует в текущем справочнике. Начните новый разбор.")
        options.append(option_for(definition))
    return sorted(options, key=lambda option: option.characteristic_id)


def _option_for_target(options: list[CharacteristicOption], search_target: str | None, query: str) -> str | None:
    """Disambiguate product scopes, never choose between properties of one product.

    Compare full lemmatized names; word order may differ ("спортивные брюки"
    vs "брюки спортивные"). No substring, score or attribute-value matching.
    """
    if not search_target:
        return None
    target = sorted(text_key(search_target).split())
    if not target:
        return None
    matches = [option for option in options if option.product_name
               and sorted(text_key(option.product_name).split()) == target]
    if matches:
        return matches[0].characteristic_id if len(matches) == 1 else None
    # The model may shorten "Зимняя шапка" to "Шапка". Recover the product
    # scope only when its complete name is explicitly present in the query.
    # Do not infer missing modifiers such as "детская" or prefer a top candidate.
    words = text_key(query).split()
    if set(words) & {"не", "ни", "без", "или", "либо"}:
        return None
    explicit = []
    for option in options:
        name = sorted(text_key(option.product_name).split()) if option.product_name else []
        if not name or not set(target).issubset(name):
            continue
        if any(sorted(words[start:start + len(name)]) == name
               for start in range(len(words) - len(name) + 1)):
            explicit.append(option)
    return explicit[0].characteristic_id if len(explicit) == 1 else None


def finish_document(request: ExtractRequest, catalog: CatalogContext, attributes: list[Attribute],
                    source_issues: list[Issue], *, search_target: str | None) -> ExtractResponse:
    debug_print("normalization.start", attributes=len(attributes))
    output = []
    questions = []
    # Rebuild catalog warnings on every request, including continuations.
    issues = [issue.model_copy(deep=True) for issue in catalog.issues if not issue.blocking]
    # Derived diagnostics (unit errors etc.) are recomputed. Unsupported query
    # fragments persist until the query is edited and extraction starts anew.
    for issue in source_issues:
        if issue.code == "unsupported_constraint":
            if issue.source_text is None or issue.source_span is None:
                raise RequestStateError("Для неподдерживаемого ограничения нужен исходный фрагмент")
            issues.append(Issue(
                id=issue.id, code="unsupported_constraint", blocking=True,
                message="Укажите конкретное значение вместо ограничения, отрицания, диапазона или альтернативы.",
                source_text=issue.source_text, source_span=issue.source_span,
            ))
    for original in attributes:
        attribute = original.model_copy(deep=True)
        options = _canonical_options(attribute, catalog)
        attribute.characteristic_options = options
        attribute.characteristic_name = None
        attribute.normalized_value = None
        attribute.message = None
        selected = attribute.characteristic_id
        if selected is None and len(options) > 1:
            # LLM aliases are suggestions, not an exhaustive dictionary. It may
            # omit the same named characteristic for the explicitly named product.
            # Recheck all definitions with these names before choosing a scope.
            names = {text_key(option.name) for option in options}
            scope_options = [option_for(definition) for definition in catalog.definitions
                             if text_key(definition.name) in names]
            selected = _option_for_target(scope_options, search_target, request.query)
            if selected is not None:
                if selected not in {option.characteristic_id for option in options}:
                    options.append(next(option for option in scope_options if option.characteristic_id == selected))
                    options.sort(key=lambda option: option.characteristic_id)
                debug_print("characteristic.selected_by_target", attribute_id=attribute.id,
                            characteristic_id=selected, search_target=search_target)
        if selected:
            definition = catalog.get_definition(selected)
            if definition is None:
                raise RequestStateError("Выбранная характеристика отсутствует в текущем справочнике")
            if options and selected not in {option.characteristic_id for option in options}:
                raise RequestStateError("Выбранная характеристика отсутствует среди вариантов этого атрибута")
            if not options:
                attribute.characteristic_options = [option_for(definition)]
        elif len(options) == 1:
            selected = options[0].characteristic_id
            definition = catalog.get_definition(selected)
        elif len(options) > 1:
            attribute.status = "needs_clarification"
            labels = [
                option.name + (f" — {option.product_name}" if option.product_name else "")
                + (f" ({', '.join(option.unit_names)})" if option.unit_names else "")
                for option in options
            ]
            questions.append(Clarification(
                id=f"{attribute.id}_characteristic", attribute_id=attribute.id, kind="choose_characteristic",
                question=f"К какой характеристике относится «{attribute.source_text}»: {' или '.join(labels)}?",
                options=options,
            ))
            output.append(attribute)
            continue
        else:
            if attribute.status != "unknown":
                raise RequestStateError("У атрибута потеряны варианты выбора. Верните исходное состояние или начните новый разбор.")
            attribute.status = "unknown"
            attribute.extracted_name = attribute.extracted_name or attribute.source_text
            attribute.message = "Неизвестная характеристика"
            output.append(attribute)
            continue

        attribute.characteristic_id = selected
        attribute.characteristic_name = definition.name
        try:
            attribute.normalized_value = normalize_value(attribute.original_value, definition)
            attribute.status = "resolved"
        except NormalizationProblem as error:
            debug_print("normalization.clarification", attribute_id=attribute.id, code=error.code, message=str(error))
            attribute.status = "needs_clarification"
            attribute.message = str(error)
            questions.append(Clarification(
                id=f"{attribute.id}_{error.kind}", attribute_id=attribute.id, kind=error.kind,
                question=str(error), suggested_values=error.suggestions,
            ))
            issues.append(Issue(
                id=f"{attribute.id}_{error.code}", code=error.code, blocking=True,
                attribute_id=attribute.id, message=str(error),
            ))
        output.append(attribute)
    return ExtractResponse(
        search_target=search_target,
        query=request.query, canonical_query=request.canonical_query,
        lemmatized_query=request.lemmatized_query,
        attributes=output, clarifications=questions, issues=issues,
        status="needs_clarification" if questions or any(issue.blocking for issue in issues) else "completed",
        input_fingerprint=input_fingerprint(request),
    )


class ExtractionService:
    def __init__(self, repository: KtruRepository, client: LMStudioClient | None = None):
        self.repository = repository
        self.client = client

    async def process(self, request: ExtractRequest) -> ExtractResponse:
        debug_print("pipeline.start", mode="initial" if request.is_initial else "continuation",
                    candidates=len(request.candidates))
        if not request.is_initial and request.input_fingerprint != input_fingerprint(request):
            raise RequestStateError("Изменился запрос/список кандидатов или отсутствует input_fingerprint. Отправьте attributes=null.")
        catalog = await asyncio.to_thread(prepare_catalog, request.candidates, self.repository)
        debug_print("catalog.loaded", definitions=len(catalog.definitions), complete=catalog.complete,
                    issues=[issue.model_dump() for issue in catalog.issues])
        if not catalog.complete:
            raise IncompleteCatalogError(catalog.issues)
        if request.is_initial:
            client = self.client or LMStudioClient(LMStudioSettings.from_env())
            draft = await extract_initial(request, catalog, client)
            debug_print("extraction.completed", search_target=draft.search_target,
                        facts=len(draft.facts), issues=[issue.model_dump() for issue in draft.issues])
            attributes = [Attribute(
                id=fact.id, source_text=fact.source_text, source_span=fact.source_span,
                mention_type=fact.mention_type, extracted_name=fact.extracted_name,
                original_value=fact.original_value,
                status="unknown" if fact.mapping_status == "unknown" else "needs_clarification",
                characteristic_id=fact.characteristic_options[0].characteristic_id if fact.mapping_status == "matched" else None,
                characteristic_options=fact.characteristic_options,
            ) for fact in draft.facts]
            return await asyncio.to_thread(finish_document, request, catalog, attributes, draft.issues,
                                           search_target=draft.search_target)
        return await asyncio.to_thread(finish_document, request, catalog, request.attributes, request.issues,
                                       search_target=request.search_target)
