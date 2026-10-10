from analyze import analyze


def rng(lo, hi, lo_incl=True, hi_incl=False):
    return {"kind": "range", "unit": "Килограмм", "lo": lo, "lo_incl": lo_incl,
            "hi": hi, "hi_incl": hi_incl}


def txt(s):
    return {"kind": "text", "text": s}


def ch(values):
    return {"type": 1, "required": False, "values": values}


def pos(code, chars):
    return {"code": code, "name": "Молоток", "chars": chars}


def make():
    return [
        pos("A", {"Масса молотка": ch([rng(0.4, 0.6), rng(0.6, 0.8)]),
                  "Материал бойка": ch([txt("Сталь"), txt("Дерево")])}),
        pos("B", {"Масса молотка": ch([rng(0.8, 1.0)]),
                  "Материал бойка": ch([txt("Сталь")])}),
        pos("C", {"Материал бойка": ch([txt("Пластик")])}),   # массы у позиции нет
    ]


def mass(v):
    return {"name": "Масса молотка", "type": "number", "value": v, "unit": "Килограмм"}


def material(s):
    return {"name": "Материал бойка", "type": "string", "value": s}


def test_ambiguous():
    r = analyze(make(), [mass(0.5)])
    assert r["status"] == "ambiguous"
    assert r["candidates"] == ["A", "C"]
    assert r["funnel"] == [{"step": "Масса молотка: 0.5 Килограмм", "before": 3, "after": 2}]


def test_resolved():
    r = analyze(make(), [mass(0.5), material("Сталь")])
    assert r["status"] == "resolved"
    assert r["result_code"] == "A"
    assert [s["after"] for s in r["funnel"]] == [2, 1]


def test_conflict_names_culprit():
    r = analyze(make(), [mass(0.9), material("Дерево")])
    assert r["status"] == "conflict"
    assert [s["after"] for s in r["funnel"]] == [2, 0]
    assert r["culprit"] == "Материал бойка: Дерево"


def test_inadequate_char_is_conflict():
    fact = {"name": "Количество ножек", "type": "number", "value": 4, "unit": None}
    r = analyze(make(), [fact])
    assert r["status"] == "conflict"
    assert r["culprit"] == "Количество ножек: 4"


def test_no_facts_keeps_everyone():
    r = analyze(make(), [])
    assert r["status"] == "ambiguous"
    assert r["candidates"] == ["A", "B", "C"]
    assert r["funnel"] == []


def test_no_candidates_has_no_culprit():
    r = analyze([], [mass(0.5)])
    assert r["status"] == "conflict"
    assert r["culprit"] is None


def test_recompute_from_scratch_does_not_mutate_input():
    cands = make()
    analyze(cands, [mass(0.5), material("Сталь")])
    r = analyze(cands, [mass(0.5)])      # второй факт «стёрли»
    assert r["candidates"] == ["A", "C"]
    assert len(cands) == 3


def test_funnel_label_for_interval():
    fact = {"name": "Масса молотка", "type": "interval", "unit": "Килограмм",
            "value": {"min": 0.5, "max": 0.7, "min_inclusive": True, "max_inclusive": False}}
    r = analyze(make(), [fact])
    assert r["funnel"][0]["step"] == "Масса молотка: [0.5; 0.7) Килограмм"
