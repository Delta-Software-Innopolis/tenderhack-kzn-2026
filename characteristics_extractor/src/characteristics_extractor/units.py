"""Explicit Russian/OKEI unit vocabulary with Decimal/Pint conversions."""

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
import math
import re

import pint


def unit_key(text: str) -> str:
    return "".join(text.casefold().replace("ё", "е").replace("²", "2").replace("³", "3").replace(".", "").split())


@dataclass(frozen=True)
class UnitSpec:
    pint_name: str
    family: str
    aliases: tuple[str, ...]


OKEI = {
    "003": UnitSpec("millimeter", "length", ("мм", "миллиметр", "миллиметры", "миллиметров", "mm")),
    "004": UnitSpec("centimeter", "length", ("см", "сантиметр", "сантиметра", "сантиметров", "cm")),
    "006": UnitSpec("meter", "length", ("м", "метр", "метра", "метров", "m")),
    "039": UnitSpec("inch", "length", ("дюйм", "дюйма", "дюймов", "дюйм (25,4 мм)", "inch", "in", '"')),
    "050": UnitSpec("millimeter**2", "area", ("мм2", "квадратный миллиметр", "mm2")),
    "163": UnitSpec("gram", "mass", ("г", "гр", "грамм", "грамма", "граммов", "g")),
    "166": UnitSpec("kilogram", "mass", ("кг", "килограмм", "килограмма", "килограммов", "kg")),
    "212": UnitSpec("watt", "power", ("вт", "ватт", "ватта", "ваттов", "w")),
    "214": UnitSpec("kilowatt", "power", ("квт", "киловатт", "киловатта", "киловаттов", "kw")),
    "222": UnitSpec("volt", "voltage", ("в", "вольт", "вольта", "вольтов", "v")),
    "2355": UnitSpec("degree", "angle", ("градус", "градусов", "градус (плоского угла)", "°", "deg")),
    "260": UnitSpec("ampere", "current", ("а", "ампер", "ампера", "амперов", "a")),
    "263": UnitSpec("ampere_hour", "charge", ("а⋅ч", "а·ч", "ач", "а*ч", "а-ч", "ампер-час", "ампер-час (3,6 ккл)", "ah")),
    "280": UnitSpec("degC", "temperature", ("°c", "°с", "градус цельсия", "градусов цельсия", "цельсий")),
    "331": UnitSpec("revolution/minute", "rotation", ("об/мин", "обмин", "оборот в минуту", "оборотов в минуту", "rpm")),
    "796": UnitSpec("piece", "count", ("шт", "штука", "штуки", "штук", "piece")),
}
EXTRA_INPUT_UNITS = (
    UnitSpec("kilometer", "length", ("км", "километр", "километров", "km")),
    UnitSpec("milligram", "mass", ("мг", "миллиграмм", "миллиграммов", "mg")),
    UnitSpec("centimeter**2", "area", ("см2", "квадратный сантиметр", "cm2")),
    UnitSpec("meter**2", "area", ("м2", "квадратный метр", "m2")),
    UnitSpec("milliampere_hour", "charge", ("мач", "ма⋅ч", "ма·ч", "mah")),
    UnitSpec("kelvin", "temperature", ("к", "кельвин", "kelvin", "k")),
    UnitSpec("degF", "temperature", ("°f", "фаренгейт", "градус фаренгейта")),
    UnitSpec("revolution/second", "rotation", ("об/с", "оборот в секунду", "rps")),
)
ALIASES = {unit_key(alias): spec for spec in (*OKEI.values(), *EXTRA_INPUT_UNITS) for alias in spec.aliases}


def unit_mentioned(unit: str, query: str) -> bool:
    """Conservative evidence check for a unit supplied by the model.

    Unknown unit vocabulary is left untouched. If another known unit is
    present, keep the value for normal validation instead of silently losing
    an explicit measurement. Aliases may be attached to a number (15см).
    """
    spec = ALIASES.get(unit_key(unit))
    if spec is None:
        return True
    aliases = {alias for known in (*OKEI.values(), *EXTRA_INPUT_UNITS) for alias in known.aliases}
    aliases.add(unit)
    return any(re.search(r"(?<![^\W\d_])" + re.escape(alias) + r"(?!\w)", query,
                         flags=re.IGNORECASE) for alias in aliases)


class UnitConversionError(ValueError):
    pass


@lru_cache(maxsize=1)
def _registry():
    registry = pint.UnitRegistry(non_int_type=Decimal)
    registry.define("piece = [item_count]")
    return registry


def json_number(value: Decimal) -> int | float:
    if not value.is_finite():
        raise UnitConversionError("Получено неконечное число")
    if value == value.to_integral_value():
        return int(value)
    result = float(value)
    if not math.isfinite(result) or (result == 0 and value != 0):
        raise UnitConversionError("Число выходит за поддерживаемый диапазон JSON")
    return result


def convert(value: int | float, source: str, target_code: str, target_name: str) -> int | float:
    source_spec = ALIASES.get(unit_key(source))
    target_spec = OKEI.get(target_code)
    # Exact same unknown unit can be retained, but cannot be converted by guesswork.
    if target_spec is None:
        if unit_key(source) == unit_key(target_name):
            return value
        raise UnitConversionError(f"Перевод в единицу «{target_name}» не настроен")
    if source_spec is None and unit_key(source) == unit_key(target_name):
        source_spec = target_spec
    if source_spec is None:
        raise UnitConversionError(f"Неизвестная единица «{source}»")
    if source_spec.family != target_spec.family:
        raise UnitConversionError(f"Единица «{source}» несовместима с «{target_name}»")
    try:
        quantity = _registry().Quantity(Decimal(str(value)), source_spec.pint_name)
        return json_number(quantity.to(target_spec.pint_name).magnitude)
    except (pint.PintError, ArithmeticError) as error:
        raise UnitConversionError("Не удалось преобразовать единицы") from error
