EPS = 1e-9   # поправка на неточность дробных чисел


def _in_range(x, v):
    if v["lo"] is not None:
        ok = x >= v["lo"] - EPS if v["lo_incl"] else x > v["lo"] + EPS
        if not ok:
            return False
    if v["hi"] is not None:
        ok = x <= v["hi"] + EPS if v["hi_incl"] else x < v["hi"] - EPS
        if not ok:
            return False
    return True


def _tighter_lo(a, b):
    """Нижняя граница пересечения двух интервалов: (значение, входит ли)."""
    if a["lo"] is None:
        return b["lo"], b["lo_incl"]
    if b["lo"] is None:
        return a["lo"], a["lo_incl"]
    if abs(a["lo"] - b["lo"]) <= EPS:
        return a["lo"], a["lo_incl"] and b["lo_incl"]
    return (a["lo"], a["lo_incl"]) if a["lo"] > b["lo"] else (b["lo"], b["lo_incl"])


def _tighter_hi(a, b):
    """Верхняя граница пересечения двух интервалов: (значение, входит ли)."""
    if a["hi"] is None:
        return b["hi"], b["hi_incl"]
    if b["hi"] is None:
        return a["hi"], a["hi_incl"]
    if abs(a["hi"] - b["hi"]) <= EPS:
        return a["hi"], a["hi_incl"] and b["hi_incl"]
    return (a["hi"], a["hi_incl"]) if a["hi"] < b["hi"] else (b["hi"], b["hi_incl"])


def _overlap(a, b):
    lo, lo_incl = _tighter_lo(a, b)
    hi, hi_incl = _tighter_hi(a, b)
    if lo is None or hi is None:
        return True
    if lo < hi - EPS:
        return True
    return abs(lo - hi) <= EPS and lo_incl and hi_incl   # граница-точка: входит с обеих сторон


def value_matches(fact, value):
    if fact["type"] == "string":
        return value["kind"] == "text" and fact["value"] == value["text"]

    if fact["type"] == "number":
        if value["kind"] not in ("number", "range"):
            return False
        x = fact["value"]
        if value["kind"] == "number":
            return abs(x - value["value"]) <= EPS
        return _in_range(x, value)

    if fact["type"] == "interval":
        v = fact["value"]
        f = {"lo": v.get("min"), "lo_incl": v.get("min_inclusive", True),
             "hi": v.get("max"), "hi_incl": v.get("max_inclusive", False)}
        if value["kind"] == "range":
            return _overlap(f, value)
        if value["kind"] == "number":
            return _in_range(value["value"], f)
        return False

    return False
