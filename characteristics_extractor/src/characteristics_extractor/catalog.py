"""Build a deterministic definition dictionary, without matching or filtering goods."""

from hashlib import sha256
import json
import unicodedata
from typing import Sequence

from pydantic import Field

from .repository import KtruCharacteristic, KtruPosition, KtruRepository, KtruValue, LoadedCatalog
from .schemas import ContractModel, Issue, Number, SearchCandidate


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _id(prefix: str, value: object) -> str:
    return f"{prefix}_{sha256(_json(value).encode('utf-8')).hexdigest()}"


def _name(value: str) -> str:
    # Only spelling presentation is folded, not synonyms, stems or dimensions.
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


class CatalogUnit(ContractModel):
    # Partial metadata is retained and diagnosed instead of inventing OKEI codes.
    okei_code: str | None
    name: str | None


class CharacteristicSource(ContractModel):
    candidate_code: str
    characteristic_row_id: int
    characteristic_code: str | None
    name: str
    is_required: int
    choice_type: int | None


class ValueSource(ContractModel):
    candidate_code: str
    characteristic_row_id: int
    value_row_id: int
    value_code: str | None


class CatalogValue(ContractModel):
    quality_description: str | None
    concrete_value: Number | None
    min_value: Number | None
    max_value: Number | None
    min_notation: str | None
    max_notation: str | None
    value_format: str | None
    unit: CatalogUnit | None
    sources: list[ValueSource] = Field(default_factory=list)


class CharacteristicDefinition(ContractModel):
    id: str
    code: str | None
    name: str
    product_name: str
    okpd2_code: str | None
    ktru_type: int | None
    kind: int | None
    units: list[CatalogUnit | None]
    sources: list[CharacteristicSource]
    values: list[CatalogValue]


class CatalogContext(ContractModel):
    candidates: list[SearchCandidate]
    definitions: list[CharacteristicDefinition]
    candidate_characteristic_ids: dict[str, list[str]]
    issues: list[Issue]

    @property
    def complete(self) -> bool:
        return not any(issue.blocking for issue in self.issues)

    def get_definition(self, characteristic_id: str) -> CharacteristicDefinition | None:
        return next((item for item in self.definitions if item.id == characteristic_id), None)

    def to_prompt_context(self) -> dict:
        """Small dictionary for extraction, not allowed ranges for product matching.

        Full numeric ranges and provenance remain available in `definitions`.
        Concrete numbers are kept because KTRU also uses numbers as category codes.
        """
        groups: dict[str, dict] = {}
        for definition in self.definitions:
            group_key = _json([_name(definition.product_name), definition.okpd2_code])
            group = groups.setdefault(group_key, {
                "product_name": definition.product_name,
                "okpd2_code": definition.okpd2_code,
                "candidate_codes": [],
                "characteristics": [],
            })
            group["candidate_codes"].extend(source.candidate_code for source in definition.sources)
            texts = sorted({v.quality_description for v in definition.values if v.quality_description is not None})
            numbers = sorted({v.concrete_value for v in definition.values if v.concrete_value is not None})
            group["characteristics"].append({
                "id": definition.id,
                "name": definition.name,
                "ktru_type": definition.ktru_type,
                "units": [unit.model_dump() if unit else None for unit in definition.units],
                "text_values": texts,
                "numeric_values": numbers,
            })
        for group in groups.values():
            group["candidate_codes"] = sorted(set(group["candidate_codes"]))
        return {"complete": self.complete, "products": [groups[key] for key in sorted(groups)]}


def _unit(value: KtruValue) -> CatalogUnit | None:
    if value.okei_code is None and value.okei_name is None:
        return None
    return CatalogUnit(okei_code=value.okei_code, name=value.okei_name)


def _units(characteristic: KtruCharacteristic) -> list[CatalogUnit | None]:
    unique = {_json(unit.model_dump() if unit else None): unit for unit in map(_unit, characteristic.values)}
    return [unique[key] for key in sorted(unique)]


def _definition_id(position: KtruPosition, characteristic: KtruCharacteristic) -> str:
    code = characteristic.code
    # Missing catalog codes are not enough evidence to merge definitions, even
    # with identical labels. Use their source identity as a conservative fallback.
    identity = code if code and code.strip() else [position.code, characteristic.id]
    return _id("char", [
        "v1", identity, _name(position.name), position.okpd2_code,
        _name(characteristic.name), characteristic.type, characteristic.kind,
        [unit.model_dump() if unit else None for unit in _units(characteristic)],
    ])


def _value_payload(value: KtruValue) -> dict:
    payload = value.model_dump(exclude={"id", "characteristic_id", "value_code", "okei_code", "okei_name"})
    unit = _unit(value)
    payload["unit"] = unit.model_dump() if unit else None
    return payload


def build_catalog(candidates: Sequence[SearchCandidate], loaded: LoadedCatalog) -> CatalogContext:
    """Coalesce only definitions with the same code, product scope, type and units."""
    positions = {position.code: position for position in loaded.positions}
    requested = list(dict.fromkeys(candidate.ktru_code for candidate in candidates))
    groups: dict[str, CharacteristicDefinition] = {}
    values: dict[str, dict[str, CatalogValue]] = {}
    candidate_ids = {code: [] for code in requested}
    issues: dict[str, Issue] = {}

    def incomplete(code: str, detail: str, blocking: bool = True) -> None:
        issue_id = _id("issue", ["incomplete_catalog", code, detail])
        issues[issue_id] = Issue(id=issue_id, code="incomplete_catalog", blocking=blocking,
                                 candidate_code=code, message=detail)

    if not requested:
        issue_id = _id("issue", ["incomplete_catalog", "empty_candidates"])
        issues[issue_id] = Issue(id=issue_id, code="incomplete_catalog", blocking=True,
                                 message="Не переданы кандидаты для построения справочника")

    for code in requested:
        position = positions.get(code)
        if position is None:
            issue_id = _id("issue", ["candidate_not_found", code])
            issues[issue_id] = Issue(id=issue_id, code="candidate_not_found", blocking=True,
                                     candidate_code=code, message=f"Кандидат {code} не найден в базе КТРУ")
            continue
        if not position.characteristics:
            incomplete(code, "У кандидата нет определений характеристик в загруженной базе", blocking=False)
        for characteristic in position.characteristics:
            definition_id = _definition_id(position, characteristic)
            source = CharacteristicSource(
                candidate_code=code, characteristic_row_id=characteristic.id,
                characteristic_code=characteristic.code, name=characteristic.name,
                is_required=characteristic.is_required, choice_type=characteristic.choice_type,
            )
            if definition_id not in groups:
                groups[definition_id] = CharacteristicDefinition(
                    id=definition_id, code=characteristic.code, name=characteristic.name,
                    product_name=position.name, okpd2_code=position.okpd2_code,
                    ktru_type=characteristic.type, kind=characteristic.kind,
                    units=_units(characteristic), sources=[], values=[],
                )
                values[definition_id] = {}
            group = groups[definition_id]
            # Deterministic official spelling when whitespace/case differ.
            group.name = min(group.name, characteristic.name)
            group.product_name = min(group.product_name, position.name)
            group.sources.append(source)
            candidate_ids[code].append(definition_id)

            if characteristic.type not in (1, 2):
                incomplete(code, f"Неизвестный тип характеристики: {characteristic.name}")
            if not characteristic.values:
                incomplete(code, f"Нет значений и единиц характеристики: {characteristic.name}")
            for value in characteristic.values:
                payload = _value_payload(value)
                key = _json(payload)
                if key not in values[definition_id]:
                    values[definition_id][key] = CatalogValue.model_validate(payload)
                values[definition_id][key].sources.append(ValueSource(
                    candidate_code=code, characteristic_row_id=characteristic.id,
                    value_row_id=value.id, value_code=value.value_code,
                ))
                if payload["unit"] is not None and (
                    not value.okei_code or not value.okei_code.strip()
                    or not value.okei_name or not value.okei_name.strip()
                ):
                    incomplete(code, f"Неполная единица ОКЕИ: {characteristic.name}")
                if all(payload[field] is None for field in (
                    "quality_description", "concrete_value", "min_value", "max_value",
                )):
                    incomplete(code, f"Пустое значение характеристики: {characteristic.name}")

    for definition_id, group in groups.items():
        group.sources.sort(key=lambda source: (source.candidate_code, source.characteristic_row_id))
        group.values = [values[definition_id][key] for key in sorted(values[definition_id])]
        for value in group.values:
            value.sources.sort(key=lambda source: (
                source.candidate_code, source.characteristic_row_id, source.value_row_id,
            ))
    return CatalogContext(
        candidates=[candidate.model_copy(deep=True) for candidate in candidates],
        definitions=[groups[key] for key in sorted(groups)],
        candidate_characteristic_ids={code: sorted(set(ids)) for code, ids in candidate_ids.items()},
        issues=[issues[key] for key in sorted(issues)],
    )


def prepare_catalog(candidates: Sequence[SearchCandidate], repository: KtruRepository) -> CatalogContext:
    return build_catalog(candidates, repository.load_positions([candidate.ktru_code for candidate in candidates]))
