from match import value_matches


def known_chars(positions):
    result = set()
    for p in positions:
        result |= set(p["chars"].keys())
    return result


def narrow(candidates, fact, known):
    name = fact["name"]

    # характеристика неадекватна для этого товара: отсеиваем всё
    if name not in known:
        return []

    result = []
    for p in candidates:
        ch = p["chars"].get(name)
        if ch is None or not ch["values"]:
            result.append(p)          # у позиции нет ограничений по этой характеристике
        elif any(value_matches(fact, v) for v in ch["values"]):
            result.append(p)          # подошло хотя бы одно допустимое значение
    return result
