"""Typed KTRU values and exact numeric comparisons; no NLP dependencies."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


# unit -> (dimension, multiplier to that dimension's base unit)
UNITS = {
    "мм": ("length", "1"), "см": ("length", "10"), "м": ("length", "1000"),
    "дюйм": ("length", "25.4"), "г": ("mass", "1"), "кг": ("mass", "1000"),
    "т": ("mass", "1000000"), "мг": ("mass", "0.001"),
    "вт": ("power", "1"), "квт": ("power", "1000"),
    "мл": ("volume", "1"), "л": ("volume", "1000"),
    "мм²": ("area", "1"), "см²": ("area", "100"), "м²": ("area", "1000000"),
    "в": ("voltage", "1"), "а": ("current", "1"), "а·ч": ("charge", "1"),
    "шт": ("count", "1"), "об/мин": ("rotation", "1"),
    "°c": ("temperature", "1"), "°": ("angle", "1"), "%": ("percent", "1"),
}
UNIT_ALIASES = {
    "миллиметр": "мм", "сантиметр": "см", "метр": "м", "дюйм": "дюйм",
    "грамм": "г", "килограмм": "кг", "тонна": "т", "миллиграмм": "мг",
    "ватт": "вт", "киловатт": "квт", "литр": "л", "миллилитр": "мл",
    "вольт": "в", "ампер": "а", "штука": "шт", "процент": "%",
    "оборот в минута": "об/мин", "оборот в минуту": "об/мин",
    "градус цельсия": "°c", "градус": "°", "ампер час": "а·ч",
    "квадратный миллиметр": "мм²", "квадратный сантиметр": "см²", "квадратный метр": "м²",
    "мм2": "мм²", "см2": "см²", "м2": "м²", "°с": "°c", "мм^2": "мм²",
    "гр": "г", "об/мин": "об/мин", "а*ч": "а·ч", "ампер-час": "а·ч",
}
OKEI = {
    "003": "мм", "004": "см", "006": "м", "039": "дюйм", "050": "мм²",
    "055": "м²", "112": "л", "163": "г", "166": "кг", "168": "т",
    "212": "вт", "214": "квт", "222": "в", "260": "а", "263": "а·ч",
    "280": "°c", "331": "об/мин", "796": "шт", "2355": "°",
}


def unit_name(name: str | None, code: str | None = None) -> str | None:
    if code in OKEI:
        return OKEI[code]
    if not name:
        return f"океи:{code}" if code else None
    name = name.lower().strip().replace("ё", "е")
    return UNIT_ALIASES.get(name, name)


def decimal(value) -> Decimal:
    try:
        result = Decimal(str(value).replace(",", "."))
    except InvalidOperation as error:
        raise ValueError(f"Некорректное число: {value}") from error
    if not result.is_finite():
        raise ValueError("Число должно быть конечным")
    return result


def json_number(value: Decimal):
    return int(value) if value == value.to_integral_value() else float(value)


def convert_value(value: dict, target_unit: str | None) -> dict:
    """Convert a query number/range for output, without replacing it by a KTRU bin."""
    source_unit = value['unit']
    source_dimension, source_factor = UNITS.get(source_unit, (source_unit, '1'))
    target_dimension, target_factor = UNITS.get(target_unit, (target_unit, '1'))
    if source_unit is not None and source_dimension != target_dimension:
        raise ValueError('Несовместимые единицы измерения')
    factor = decimal(source_factor) / decimal(target_factor) if source_unit is not None else decimal(1)
    converted = dict(value, unit=target_unit)
    if value['type'] == 'number':
        converted['value'] = json_number(decimal(value['value']) * factor)
    else:
        converted['value'] = {**value['value'], **{
            bound: json_number(decimal(value['value'][bound]) * factor)
            if value['value'][bound] is not None else None for bound in ('min', 'max')
        }}
    return converted


def interval(minimum=None, maximum=None, min_inclusive=True, max_inclusive=True):
    low = decimal(minimum) if minimum is not None else None
    high = decimal(maximum) if maximum is not None else None
    if low is None and high is None:
        raise ValueError("У интервала должна быть хотя бы одна граница")
    if low is not None and high is not None:
        if low > high or (low == high and not (min_inclusive and max_inclusive)):
            raise ValueError("Пустой или обратный интервал")
    return {
        "min": json_number(low) if low is not None else None,
        "max": json_number(high) if high is not None else None,
        "min_inclusive": bool(min_inclusive) if low is not None else False,
        "max_inclusive": bool(max_inclusive) if high is not None else False,
    }


def from_db(name: str, row: dict) -> list[dict]:
    """One DB row may contain several representations; do not drop any of them."""
    base = {"name": name, "unit": unit_name(row["okei_name"], row["okei_code"]),
            "value_code": row["value_code"]}
    result = []
    if row["quality_description"] is not None:
        result.append({**base, "type": "string", "value": row["quality_description"]})
    if row["concrete_value"] is not None:
        result.append({**base, "type": "number", "value": json_number(decimal(row["concrete_value"]))})
    if row["min_value"] is not None or row["max_value"] is not None:
        if row["min_value"] is not None and row["min_notation"] not in ("greater", "greaterOrEqual"):
            raise ValueError("Неизвестное условие нижней границы КТРУ")
        if row["max_value"] is not None and row["max_notation"] not in ("less", "lessOrEqual"):
            raise ValueError("Неизвестное условие верхней границы КТРУ")
        result.append({**base, "type": "interval", "value": interval(
            row["min_value"], row["max_value"],
            row["min_notation"] == "greaterOrEqual", row["max_notation"] == "lessOrEqual",
        )})
    if not result:
        raise ValueError("У характеристики отсутствует представление значения")
    return result


def _bounds(value: dict, unit: str | None):
    factor = decimal(UNITS.get(unit, (unit, "1"))[1])
    if value["type"] == "number":
        point = decimal(value["value"]) * factor
        return point, point, True, True
    data = value["value"]
    return (
        decimal(data["min"]) * factor if data["min"] is not None else Decimal("-Infinity"),
        decimal(data["max"]) * factor if data["max"] is not None else Decimal("Infinity"),
        data["min_inclusive"], data["max_inclusive"],
    )


def _contains(outer, inner):
    a, b, ai, bi = outer
    c, d, ci, di = inner
    return (a < c or a == c and (ai or not ci)) and (b > d or b == d and (bi or not di))


def _overlaps(a, b):
    return not (a[1] < b[0] or b[1] < a[0]
                or a[1] == b[0] and not (a[3] and b[2])
                or b[1] == a[0] and not (b[3] and a[2]))


def compare_numeric(query: dict, allowed: list[dict]) -> dict:
    """Compare against the union of alternatives, without bridging gaps."""
    numeric = [value for value in allowed if value["type"] in ("number", "interval")]
    if not numeric:
        return {"status": "value_mismatch", "reason": "В КТРУ нет числовых значений"}
    unit = query.get("unit")
    inferred = False
    if unit is None:
        units = {value["unit"] for value in numeric}
        if len(units) != 1:
            return {"status": "ambiguous", "reason": "Укажите единицу измерения"}
        unit = next(iter(units))
        inferred = unit is not None
    dimension = UNITS.get(unit, (unit, "1"))[0]
    compatible = [value for value in numeric
                  if UNITS.get(value["unit"], (value["unit"], "1"))[0] == dimension]
    if not compatible:
        return {"status": "unit_mismatch", "reason": "Несовместимые единицы измерения"}
    requested = _bounds(query, unit)
    ranges = sorted((_bounds(value, value["unit"]) for value in compatible),
                    key=lambda b: (b[0], not b[2], b[1]))
    merged = []
    for current in ranges:
        if not merged or (merged[-1][1] < current[0] or
                          merged[-1][1] == current[0] and not (merged[-1][3] or current[2])):
            merged.append(current)
            continue
        previous = merged[-1]
        if current[1] > previous[1]:
            merged[-1] = previous[0], current[1], previous[2], current[3]
        elif current[1] == previous[1]:
            merged[-1] = previous[0], previous[1], previous[2], previous[3] or current[3]
    if query.get("negated"):
        status = "matched" if any(not _contains(requested, value) for value in merged) else "value_mismatch"
    elif any(_contains(value, requested) for value in merged):
        status = "matched"
    elif any(_overlaps(value, requested) for value in merged):
        status = "partial_match"
    else:
        status = "value_mismatch"
    return {"status": status, "comparison_unit": unit, "unit_inferred": inferred}
