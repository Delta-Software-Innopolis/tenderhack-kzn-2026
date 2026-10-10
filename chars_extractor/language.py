"""Candidate-guided Russian extraction rules. Models are never loaded here."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

if __package__:
    from .values import UNITS, UNIT_ALIASES, decimal, interval, json_number, unit_name
else:
    from values import UNITS, UNIT_ALIASES, decimal, interval, json_number, unit_name


ALIASES = {
    "ручка": "рукоятка", "рукоять": "рукоятка", "вес": "масса",
    "деревянный": "дерево", "древесина": "дерево", "резиновый": "резина",
    "пластиковый": "пластик", "пластмасса": "пластик", "пластмассовый": "пластик",
    "металлический": "металл", "стальной": "сталь", "алюминиевый": "алюминий",
    "хлопковый": "хлопок", "кожаный": "кожа", "шерстяной": "шерсть",
    "женщина": "женский", "мужчина": "мужской",
    "нейлоновый": "нейлон", "полиэстеровый": "полиэстер",
    "основный": "основной",
}
MATERIALS = set("дерево резина пластик металл сталь алюминий хлопок кожа шерсть нейлон полиэстер акрил латекс кевлар полиэфир".split())
COLORS = set("красный синий зеленый желтый черный белый серый коричневый оранжевый".split())
SHAPES = set("круглый квадратный прямоугольный овальный".split())
PARTS = set("рукоятка боек головка корпус столешница каркас подошва верх подкладка сиденье спинка".split())
HEADS = set("длина ширина высота глубина диаметр масса материал цвет форма размер мощность напряжение емкость температура количество пол назначение тип покрытие износостойкость твердость плотность толщина".split())
PURPOSES = {"строительный", "медицинский", "офисный", "спортивный"}
STOP = {"в", "на", "с", "со", "из", "для", "по", "и", "у"}
TOKEN = re.compile(r"\d+(?:[.,]\d+)?|[а-яёa-z]+[²2]?|>=|<=|[<>≤≥=]|[^\w\s]", re.I)
NUMBER = r"[+-]?\d+(?:[.,]\d+)?"


@lru_cache(maxsize=1)
def _morph():
    import pymorphy3
    return pymorphy3.MorphAnalyzer()


@lru_cache(maxsize=20000)
def lemma(word: str) -> str:
    word = word.lower().replace("ё", "е")
    # The normalized noun is otherwise mistaken for the short adjective "бойкий".
    if word == "боек":
        return word
    if not word.isalpha():
        return word
    return _morph().parse(word)[0].normal_form.replace("ё", "е")


def canonical(text: str) -> tuple[str, ...]:
    words = [ALIASES.get(lemma(match.group()), lemma(match.group()))
             for match in TOKEN.finditer(text) if match.group()[0].isalnum()]
    words = [word for word in words if word not in STOP]
    if "материал" in words:
        words = [word for word in words if word not in ("вид", "тип")]
    if "половой" in words and any(w in words for w in ("принадлежность", "признак")):
        words = ["пол"]
    return tuple(words)


def name_key(text: str) -> tuple[str, ...]:
    return tuple(sorted(canonical(text)))


@dataclass(frozen=True)
class Token:
    text: str
    norm: str
    start: int
    end: int


def _tokens(text: str) -> list[Token]:
    return [Token(m.group(), ALIASES.get(lemma(m.group()), lemma(m.group())), m.start(), m.end())
            for m in TOKEN.finditer(text)]


def _unit(text: str):
    """Return (canonical unit, consumed characters). Unknown units stay explicit."""
    tokens = _tokens(text)
    for size in range(min(4, len(tokens)), 0, -1):
        raw = text[:tokens[size-1].end].strip().lower()
        normalized = " ".join(lemma(t.text) for t in tokens[:size])
        for spelling in (raw, normalized):
            if spelling in UNITS or spelling in UNIT_ALIASES:
                return unit_name(spelling), tokens[size-1].end
    if tokens and tokens[0].text.isalpha() and tokens[0].norm not in STOP | {"не", "или"}:
        return tokens[0].norm, tokens[0].end
    return None, 0


def _numeric(text: str):
    """Parse numbers, one-sided constraints and ranges, retaining boundary semantics."""
    offset = len(text) - len(text.lstrip(" :="))
    value_text = text[offset:].lower().replace("≤", "<=").replace("≥", ">=")
    patterns = [
        rf"от\s+({NUMBER})\s*(.*?)\s*до\s+({NUMBER})",
        rf"({NUMBER})\s*([а-яa-z²°%·/]*?)\s*[-–—]\s*({NUMBER})",
    ]
    for pattern in patterns:
        match = re.match(pattern, value_text)
        if match:
            first, raw_unit, last = match.groups()
            second_unit, used = _unit(value_text[match.end():])
            first_unit, _ = _unit(raw_unit)
            low, high = decimal(first), decimal(last)
            result_unit = second_unit or first_unit
            if first_unit and second_unit and first_unit != second_unit:
                if first_unit not in UNITS or second_unit not in UNITS or UNITS[first_unit][0] != UNITS[second_unit][0]:
                    raise ValueError("Разные размерности у границ интервала")
                low *= decimal(UNITS[first_unit][1]) / decimal(UNITS[second_unit][1])
            return {"type": "interval", "value": interval(low, high), "unit": result_unit}, offset + match.end() + used
    comparison = re.match(
        r"(не\s+(?:менее|меньше|маленький)|не\s+(?:более|больше|большой)|"
        r"более|больше|большой|менее|меньше|маленький|>=|<=|>|<|от|до)\s*", value_text,
    )
    prefix = comparison.end() if comparison else 0
    number = re.match(NUMBER, value_text[prefix:])
    if not number:
        return None
    number_end = prefix + number.end()
    unit, used = _unit(value_text[number_end:])
    amount = json_number(decimal(number.group()))
    if comparison:
        operator = comparison.group(1)
        lower = operator in {">", ">=", "более", "больше", "большой", "от"} or operator.startswith(("не менее", "не меньше", "не маленький"))
        inclusive = operator in {">=", "<=", "от", "до"} or operator.startswith("не ")
        value = interval(amount, None, inclusive, False) if lower else interval(None, amount, False, inclusive)
        return {"type": "interval", "value": value, "unit": unit}, offset + number_end + used
    return {"type": "number", "value": amount, "unit": unit}, offset + number_end + used


def _labels(tokens: list[Token], names: list[str], product_words: set[str], value_words: set[str]):
    forms = {name_key(name) for name in names}
    forms.update(tuple(word for word in form if word != "наличие") for form in list(forms)
                 if "наличие" in form)
    forms.update((head,) for head in HEADS)
    forms.update(tuple(sorted((head, part))) for head in HEADS for part in PARTS)
    for name in names:
        words = canonical(name)
        for index, word in enumerate(words[:-1]):
            if word in {'основной', 'дополнительный'}:
                forms.add(tuple(sorted(words[index:index + 2])))
    # A component followed by a measurement is a label even without "длина".
    # Also retain explicitly named unknown numeric properties ("ресурс 100 цикл").
    for index, token in enumerate(tokens[:-1]):
        following = tokens[index + 1].text
        if (token.text.isalpha() and token.norm not in product_words | STOP | PURPOSES | value_words | MATERIALS
                and token.norm not in UNIT_ALIASES and token.norm not in UNITS
                and (following[0].isdigit() or following in {":", "=", ">", "<", ">=", "<=", "от", "до"})
                and (token.norm in PARTS or "NOUN" in _morph().parse(token.text)[0].tag)):
            forms.add((token.norm,))
        elif (token.text.isalpha() and token.norm not in product_words | STOP | PARTS | PURPOSES | value_words | MATERIALS
              and token.norm not in UNITS and token.norm not in UNIT_ALIASES
              and 'NOUN' in _morph().parse(token.text)[0].tag
              and ('ADJF' in _morph().parse(following)[0].tag or 'ADJS' in _morph().parse(following)[0].tag)):
            forms.add((token.norm,))
    max_words = max((len(form) for form in forms), default=1)
    labels = []
    start = 0
    while start < len(tokens):
        if (tokens[start].norm in PARTS and start > 0
                and tokens[start-1].norm in MATERIALS | COLORS | SHAPES | {"прорезиненный"}):
            start += 1
            continue
        words = []
        best = None
        for end in range(start, min(len(tokens), start + max_words + 3)):
            token = tokens[end]
            if not token.text.isalpha() or token.norm in {"не", "без", "от", "до"}:
                break
            if token.norm not in STOP:
                words.append(token.norm)
            if words and tuple(sorted(words)) in forms and tokens[start].norm not in STOP:
                best = end + 1
        if best is not None:
            labels.append((start, best))
            start = best
        else:
            start += 1
    return labels


def extract(query: str, definitions: list[dict], product_names=()):
    """Extract facts with source spans; unresolved fragments are retained separately."""
    tokens = _tokens(query)
    names = list(dict.fromkeys(c["name"] for c in definitions))
    product_words = {word for name in product_names for word in canonical(name)}
    value_words = {word for c in definitions for v in c['values'] if v['type'] == 'string'
                   for word in canonical(v['value'])}
    labels = _labels(tokens, names, product_words, value_words)
    extracted, issues, occupied = [], [], set()

    def add(name, data, start, end, possible_names=None):
        entry = {"name": name, **data, "source": query[start:end], "start": start, "end": end}
        if possible_names:
            entry["possible_names"] = possible_names
        extracted.append(entry)
        occupied.update(range(start, end))

    for index, (start, end) in enumerate(labels):
        begin, label_end = tokens[start].start, tokens[end-1].end
        stop = tokens[labels[index+1][0]].start if index+1 < len(labels) else len(query)
        separator = re.search(r"[,;\n](?!\d)", query[label_end:stop])
        if separator:
            stop = label_end + separator.start()
        raw = query[label_end:stop].strip(" :=,;\n")
        name = query[begin:label_end]
        # "Без капюшона" / "с капюшоном" is a boolean requirement, not a missing value.
        related = [c for c in definitions if set(name_key(name)) <= set(name_key(c["name"]))]
        boolean = related and all(c["values"] and all(
            v["type"] == "string" and canonical(v["value"]) in {("да",), ("нет",)}
            for v in c["values"]
        ) for c in related)
        if boolean and start and tokens[start-1].norm in {"без", "с"}:
            add(name, {"type": "string", "value": "нет" if tokens[start-1].norm == "без" else "да",
                       "unit": None}, tokens[start-1].start, label_end)
            continue
        if not raw:
            # A preceding material/color adjective is handled by the implicit pass.
            if start and tokens[start-1].norm in MATERIALS | COLORS | SHAPES:
                continue
            issues.append({"source": query[begin:stop], "start": begin, "end": stop,
                           "reason": "Не указано значение характеристики"})
            occupied.update(range(begin, stop))
            continue
        try:
            negative = raw.startswith("не ") and not re.match(r"не\s+(менее|более|меньше|больше|маленький|большой)", raw)
            value_text = raw[3:] if negative else raw
            # Digit-like categorical values (e.g. shoe size) remain strings.
            related = [c for c in definitions if name_key(c["name"]) == name_key(name)]
            categorical = related and all(c["values"] and all(v["type"] == "string" for v in c["values"]) for c in related)
            numeric = None if categorical else _numeric(value_text)
            if numeric:
                data, used = numeric
                remaining = value_text[used:].strip(" ,;.")
                if remaining and remaining != "и":
                    raise ValueError("Неоднозначное числовое выражение или неподдерживаемый остаток")
            else:
                if not categorical and re.search(r"\d", value_text) and (value_text.startswith(("от ", "до ", ">", "<"))):
                    raise ValueError("Не удалось разобрать числовое ограничение")
                data = {"type": "string", "value": value_text.rstrip(" ,;."), "unit": None}
            if negative:
                data["negated"] = True
            hints = None
            if numeric and len(name_key(name)) == 1 and name_key(name)[0] in PARTS:
                part = name_key(name)[0]
                dimension = UNITS.get(data['unit'], (data['unit'],))[0]
                compatible_names = sorted({c['name'] for c in definitions
                    if part in name_key(c['name']) and any(
                        v['type'] in {'number', 'interval'} and
                        (data['unit'] is None or UNITS.get(v['unit'], (v['unit'],))[0] == dimension)
                        for v in c['values'])})
                if compatible_names:
                    name = compatible_names[0] if len(compatible_names) == 1 else name
                    hints = compatible_names
                else:
                    # Keep a measurable component even if it is absent in this catalogue.
                    name = f"{'длина' if dimension == 'length' else 'размер'} {part}"
            add(name, data, begin, stop, hints)
        except ValueError as error:
            issues.append({"source": query[begin:stop], "start": begin, "end": stop, "reason": str(error)})
            occupied.update(range(begin, stop))

    # Values can occur without an explicit characteristic name: "круглый боек".
    strings = {}
    for definition in definitions:
        for value in definition["values"]:
            if value["type"] == "string":
                key = canonical(value["value"])
                if key and key not in {("да",), ("нет",)}:
                    strings.setdefault(key, set()).add(definition["name"])
    for token in tokens:
        if token.norm in MATERIALS | COLORS | SHAPES | {"прорезиненный"}:
            strings.setdefault((token.norm,), set())
    for start, token in enumerate(tokens):
        if any(p in occupied for p in range(token.start, token.end)):
            continue
        choices = []
        for phrase, applicable_names in strings.items():
            end = start + len(phrase)
            if end > len(tokens) or tuple(t.norm for t in tokens[start:end]) != phrase:
                continue
            if any(p in occupied for p in range(token.start, tokens[end-1].end)):
                continue
            choices.append((end, applicable_names))
        if not choices:
            continue
        end, applicable_names = max(choices, key=lambda choice: choice[0])
        value = query[token.start:tokens[end-1].end]
        part = None
        if end < len(tokens) and tokens[end].norm in PARTS and tokens[end].start not in occupied:
            part = tokens[end].norm
            end += 1
        elif start > 0 and tokens[start-1].norm in PARTS and tokens[start-1].start not in occupied:
            part = tokens[start-1].norm
            start -= 1
        if token.norm in MATERIALS:
            name, value = "материал", token.norm
        elif token.norm in COLORS:
            name = "цвет"
        elif token.norm in SHAPES:
            name = "форма"
        elif token.norm == "прорезиненный":
            name, value = "покрытие", "резина"
        else:
            name = next(iter(applicable_names)) if len(applicable_names) == 1 else value
        if part:
            name = f"{name} {part}" if name in {"материал", "цвет", "форма", "покрытие"} else name
            applicable_names = {n for n in applicable_names if part in canonical(n)}
        begin = tokens[start].start
        negated = start > 0 and tokens[start-1].norm == "не"
        if negated:
            begin = tokens[start-1].start
        data = {"type": "string", "value": value, "unit": None}
        if negated:
            data["negated"] = True
        # Explicit component words take priority over a globally ambiguous value.
        hints = sorted(applicable_names) if not part and applicable_names else None
        if hints and not negated:
            # An implicit value without a component/role means "any matching field",
            # not simultaneous requirements on every field that permits the value.
            data['match_mode'] = 'any'
        add(name, data, begin, tokens[end-1].end, hints)

    # Purpose adjectives absent from allowed values must not disappear entirely.
    # Do not force "строительный" into a catalogue's unrelated Type enumeration.
    for token in tokens:
        if token.norm in PURPOSES and not any(p in occupied for p in range(token.start, token.end)):
            add('назначение', {'type': 'string', 'value': token.norm, 'unit': None}, token.start, token.end)

    extracted.sort(key=lambda c: c["start"])
    return extracted, issues, occupied
