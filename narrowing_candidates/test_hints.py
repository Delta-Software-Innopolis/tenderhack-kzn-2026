from analyze import analyze
from hints import make_hints
from narrow import known_chars


def rng(lo, hi, lo_incl=True, hi_incl=False):
    return {"kind": "range", "unit": "Килограмм", "lo": lo, "lo_incl": lo_incl,
            "hi": hi, "hi_incl": hi_incl}


def txt(s):
    return {"kind": "text", "text": s}


def ch(values, required=False):
    return {"type": 1, "required": required, "values": values}


def pos(code, chars):
    return {"code": code, "name": "Молоток", "chars": chars}


COLORS = [txt("Красный"), txt("Синий")]

# «Безынерционный» делит 4 позиции пополам, «Цвет» у всех одинаковый (бесполезный)
P_ALL = [
    pos("P1", {"Безынерционный": ch([txt("Да")]),  "Цвет": ch(COLORS)}),
    pos("P2", {"Безынерционный": ch([txt("Нет")]), "Цвет": ch(COLORS)}),
    pos("P3", {"Безынерционный": ch([txt("Да")]),  "Цвет": ch(COLORS)}),
    pos("P4", {"Безынерционный": ch([txt("Нет")]), "Цвет": ch(COLORS)}),
]


def test_useless_char_skipped_useful_char_suggested():
    hints = make_hints(P_ALL, [], known_chars(P_ALL))
    assert [h["name"] for h in hints] == ["Безынерционный"]
    h = hints[0]
    assert [(o["label"], o["remaining"]) for o in h["options"]] == [("Да", 2), ("Нет", 2)]
    assert h["options"][0]["fact"] == {"name": "Безынерционный", "type": "string", "value": "Да"}


def test_required_char_goes_first_even_with_worse_average():
    Q = [
        pos("Q1", {"Тип": ch([txt("Столярный")], True), "Материал": ch([txt("Сталь")])}),
        pos("Q2", {"Тип": ch([txt("Слесарный")], True),  "Материал": ch([txt("Дерево")])}),
        pos("Q3", {"Тип": ch([txt("Слесарный")], True),  "Материал": ch([txt("Пластик")])}),
        pos("Q4", {"Тип": ch([txt("Столярный")], True), "Материал": ch([txt("Пластик")])}),
    ]
    hints = make_hints(Q, [], known_chars(Q))
    # у «Материала» средний остаток лучше (1.33 против 2.0), но «Тип» обязательный
    assert [h["name"] for h in hints] == ["Тип", "Материал"]


def test_already_used_char_is_not_suggested():
    fact = {"name": "Безынерционный", "type": "string", "value": "Да"}
    assert make_hints(P_ALL, [fact], known_chars(P_ALL)) == []


def test_range_options_become_interval_facts():
    R = [
        pos("R1", {"Масса молотка": ch([rng(0.4, 0.6)])}),
        pos("R2", {"Масса молотка": ch([rng(0.6, 0.8)])}),
        pos("R3", {"Масса молотка": ch([rng(0.4, 0.6), rng(0.6, 0.8)])}),
    ]
    hints = make_hints(R, [], known_chars(R))
    h = hints[0]
    assert h["name"] == "Масса молотка"
    assert [o["label"] for o in h["options"]] == ["[0.4; 0.6) Килограмм", "[0.6; 0.8) Килограмм"]
    assert [o["remaining"] for o in h["options"]] == [2, 2]
    assert h["options"][0]["fact"]["type"] == "interval"


def test_hints_only_when_ambiguous():
    assert analyze([P_ALL[0]], [])["hints"] == []                       # resolved
    assert analyze(P_ALL, [])["hints"] != []                             # ambiguous


def test_indistinguishable_positions_have_no_hints():
    fact = {"name": "Безынерционный", "type": "string", "value": "Да"}
    r = analyze(P_ALL, [fact])        # остаются P1 и P3: одинаковые по всем характеристикам
    assert r["status"] == "ambiguous"
    assert r["candidates"] == ["P1", "P3"]
    assert r["hints"] == []
