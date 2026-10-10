"""Normalize one selected definition; never compare a value with product ranges."""

from functools import lru_cache
import re

import pymorphy3

from .catalog import CharacteristicDefinition
from .schemas import NormalizedNumber, NormalizedString, OkeiUnit, OriginalValue
from .units import UnitConversionError, convert


class NormalizationProblem(ValueError):
    def __init__(self, message: str, *, kind="specify_value", code="unmapped_value", suggestions=()):
        self.kind = kind
        self.code = code
        self.suggestions = list(suggestions)
        super().__init__(message)


@lru_cache(maxsize=1)
def _morph():
    return pymorphy3.MorphAnalyzer()


@lru_cache(maxsize=4096)
def text_key(text: str) -> str:
    words = re.findall(r"[\w]+", text.casefold().replace("ё", "е"))
    return " ".join(_morph().parse(word)[0].normal_form for word in words)


# Whole-value synonyms only. Rubber coating does not imply a rubber handle.
TEXT_ALIASES = {
    "стальной": "сталь", "алюминиевый": "алюминий", "медный": "медь",
    "деревянный": "дерево", "пластиковый": "пластик", "резиновый": "резина",
}


def normalize_value(value: OriginalValue, definition: CharacteristicDefinition):
    if definition.ktru_type == 1:
        variants = sorted({v.quality_description for v in definition.values if v.quality_description is not None})
        if value.type == "boolean":
            raw = "Да" if value.value else "Нет"
        elif value.type == "string":
            raw = value.value
        else:
            raise NormalizationProblem("Для этой характеристики требуется текстовое значение", suggestions=variants)
        key = text_key(raw)
        aliased_key = text_key(TEXT_ALIASES.get(key, raw))
        matches = [variant for variant in variants if text_key(variant) in {key, aliased_key}]
        if len(matches) != 1:
            raise NormalizationProblem(
                "Не удалось однозначно привести значение к справочнику. Уточните значение характеристики.",
                suggestions=variants,
            )
        return NormalizedString(type="string", value=matches[0])

    if definition.ktru_type != 2 or value.type != "number":
        raise NormalizationProblem("Укажите конкретное числовое значение характеристики")
    units = definition.units
    if units == [None]:
        if value.unit is not None:
            raise NormalizationProblem("Характеристика безразмерная. Укажите число без единицы.",
                                       kind="specify_unit", code="incompatible_unit")
        return NormalizedNumber(type="number", value=value.value, unit=None)
    targets = sorted((unit for unit in units if unit and unit.okei_code and unit.name), key=lambda unit: unit.okei_code)
    if not targets:
        raise NormalizationProblem("В справочнике не определены единицы характеристики", code="incomplete_catalog")
    if value.unit is None:
        raise NormalizationProblem("Укажите единицу исходного числа", kind="specify_unit", code="incompatible_unit",
                                   suggestions=[target.name for target in targets])
    errors = []
    # Choose a deterministic compatible catalog unit, not the first candidate's unit.
    for target in targets:
        try:
            number = convert(value.value, value.unit, target.okei_code, target.name)
            return NormalizedNumber(type="number", value=number,
                                    unit=OkeiUnit(okei_code=target.okei_code, name=target.name))
        except UnitConversionError as error:
            errors.append(str(error))
    raise NormalizationProblem(errors[0], kind="specify_unit", code="incompatible_unit",
                               suggestions=[target.name for target in targets])
