from match import value_matches


def known_chars(positions):
    result = set()
    for p in positions:
        result |= set(p["chars"].keys())
    return result


def narrow(candidates, fact, known):
    name = fact["name"]
    print("Name!", name)

    # характеристика неадекватна для этого товара: отсеиваем всё
    if name not in known:
        return []

    result = []
    for p in candidates:
        ch = p["chars"].get(name)
        # print("CH!", ch)
        if ch is None or not ch["values"]:
            print(1)
            result.append(p)          # у позиции нет ограничений по этой характеристике
        elif any(value_matches(fact, v) for v in ch["values"]):
            print("бурмалда")
            print(ch["values"])
            print(2)
            result.append(p)          # подошло хотя бы одно допустимое значение
    return result
