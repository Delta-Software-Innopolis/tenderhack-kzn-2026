from match import value_matches


# значения из справочника (внутренний формат)
def rng(lo, hi, lo_incl=True, hi_incl=False, unit="Килограмм"):
    return {"kind": "range", "unit": unit, "lo": lo, "lo_incl": lo_incl,
            "hi": hi, "hi_incl": hi_incl}

def num(v, unit=None):
    return {"kind": "number", "value": v, "unit": unit}

def txt(s):
    return {"kind": "text", "text": s}


# факты от шага 3 (формат ребят)
def fnum(v, unit="Килограмм"):
    return {"name": "x", "type": "number", "value": v, "unit": unit}

def ftxt(s):
    return {"name": "x", "type": "string", "value": s}

def fint(lo, hi, lo_incl=True, hi_incl=False):
    return {"name": "x", "type": "interval", "unit": "Килограмм",
            "value": {"min": lo, "max": hi, "min_inclusive": lo_incl, "max_inclusive": hi_incl}}


def test_inside_range():
    assert value_matches(fnum(0.5), rng(0.4, 0.6))

def test_lower_bound_included():
    assert value_matches(fnum(0.4), rng(0.4, 0.6))

def test_upper_bound_excluded():
    assert not value_matches(fnum(0.6), rng(0.4, 0.6))

def test_upper_bound_included_when_notation_says_so():
    assert value_matches(fnum(0.6), rng(0.4, 0.6, hi_incl=True))

def test_lower_bound_excluded_when_notation_says_so():
    assert not value_matches(fnum(0.4), rng(0.4, 0.6, lo_incl=False))

def test_open_lower_bound():
    assert value_matches(fnum(0.05), rng(None, 0.1, lo_incl=False))
    assert not value_matches(fnum(0.1), rng(None, 0.1, lo_incl=False))

def test_open_upper_bound():
    assert value_matches(fnum(100), rng(2.5, None, hi_incl=False))

def test_unit_is_ignored():
    assert value_matches(fnum(0.5, "что угодно"), rng(0.4, 0.6))

def test_fact_without_unit_compared_as_is():
    assert value_matches(fnum(0.5, None), rng(0.4, 0.6))

def test_number_vs_number():
    assert value_matches(fnum(3, None), num(3.0))
    assert not value_matches(fnum(4, None), num(3.0))

def test_text_exact_match():
    assert value_matches(ftxt("Сталь"), txt("Сталь"))
    assert not value_matches(ftxt("Дерево"), txt("Сталь"))

def test_kind_mismatch():
    assert not value_matches(ftxt("Сталь"), rng(0.4, 0.6))
    assert not value_matches(fnum(5, None), txt("Сталь"))


# интервалы
def test_interval_overlaps_range():
    assert value_matches(fint(0.3, 0.5), rng(0.4, 0.6))
    assert value_matches(fint(0.45, 0.5), rng(0.4, 0.6))
    assert not value_matches(fint(0.7, 0.9), rng(0.4, 0.6))

def test_interval_touching_at_excluded_bound():
    assert not value_matches(fint(0.6, 0.8), rng(0.4, 0.6))

def test_interval_touching_at_included_bound():
    assert value_matches(fint(0.6, 0.8), rng(0.4, 0.6, hi_incl=True))

def test_interval_open_bounds():
    assert value_matches(fint(2.0, None), rng(2.5, None))
    assert value_matches(fint(None, 0.5), rng(0.4, 0.6))

def test_interval_vs_number_value():
    assert value_matches(fint(100, 200), num(150))
    assert not value_matches(fint(100, 200), num(200))

def test_interval_vs_text():
    assert not value_matches(fint(1, 2), txt("Сталь"))
