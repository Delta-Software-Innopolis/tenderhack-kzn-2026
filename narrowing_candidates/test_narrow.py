from narrow import narrow, known_chars


def rng(lo, hi, lo_incl=True, hi_incl=False):
    return {"kind": "range", "unit": "Килограмм", "lo": lo, "lo_incl": lo_incl,
            "hi": hi, "hi_incl": hi_incl}


def txt(s):
    return {"kind": "text", "text": s}


def ch(values):
    return {"type": 1, "required": False, "values": values}


A = {"code": "A", "name": "Молоток", "chars": {
    "Масса молотка": ch([rng(0.4, 0.6), rng(0.6, 0.8)]),
    "Материал бойка": ch([txt("Сталь"), txt("Дерево")]),
}}
B = {"code": "B", "name": "Молоток", "chars": {
    "Масса молотка": ch([rng(0.8, 1.0)]),
    "Материал бойка": ch([txt("Сталь")]),
}}
C = {"code": "C", "name": "Молоток", "chars": {      # массы у позиции нет
    "Материал бойка": ch([txt("Пластик")]),
}}

POS = [A, B, C]
KNOWN = known_chars(POS)


def codes(lst):
    return [p["code"] for p in lst]


def test_known_chars():
    assert KNOWN == {"Масса молотка", "Материал бойка"}


def test_number_fact_against_ranges():
    fact = {"name": "Масса молотка", "type": "number", "value": 0.5, "unit": "Килограмм"}
    # A: 0.5 в [0.4; 0.6) ; B: не входит ; C: массы нет, но она адекватна, остаётся
    assert codes(narrow(POS, fact, KNOWN)) == ["A", "C"]


def test_text_fact():
    fact = {"name": "Материал бойка", "type": "string", "value": "Сталь"}
    # C: характеристика есть, но значение «Пластик» не подходит, отсеивается
    assert codes(narrow(POS, fact, KNOWN)) == ["A", "B"]


def test_inadequate_char_removes_everything():
    fact = {"name": "Количество ножек", "type": "number", "value": 4, "unit": None}
    assert narrow(POS, fact, KNOWN) == []


def test_empty_values_list_keeps_position():
    D = {"code": "D", "name": "Молоток", "chars": {"Масса молотка": ch([])}}
    known = known_chars([D])
    fact = {"name": "Масса молотка", "type": "number", "value": 5, "unit": "Килограмм"}
    assert codes(narrow([D], fact, known)) == ["D"]


def test_interval_fact():
    fact = {"name": "Масса молотка", "type": "interval", "unit": "Килограмм",
            "value": {"min": 0.5, "max": 0.9, "min_inclusive": True, "max_inclusive": False}}
    # A: [0.4; 0.6) и [0.6; 0.8) пересекаются; B: [0.8; 1.0) пересекается; C: массы нет, остаётся
    assert codes(narrow(POS, fact, KNOWN)) == ["A", "B", "C"]
