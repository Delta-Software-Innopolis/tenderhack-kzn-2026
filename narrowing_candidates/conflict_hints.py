"""Подсказки для случаев, которых нет в hints.make_hints:
  * conflict  — воронка дала 0 позиций  -> make_conflict_hints
  * ambiguous — позиций несколько, но make_hints ничего не предложил -> make_indistinguishable_hint

Использует только narrow(candidates, fact, known) и hints._options.
Формат подсказки похож на make_hints: у вариантов есть готовый "fact", который
можно отправить обратно в движок, и "remaining" — сколько позиций останется.
"""
import json
from difflib import get_close_matches
from itertools import combinations

from hints import _options
from narrow import narrow


# ---------- вспомогательное ----------

def _fmt_fact(f):
    name, unit = f["name"], f.get("unit")
    if f["type"] == "interval":
        v = f["value"]
        lb = "[" if v.get("min_inclusive", True) else "("
        rb = "]" if v.get("max_inclusive", True) else ")"
        lo = "-∞" if v["min"] is None else v["min"]
        hi = "∞" if v["max"] is None else v["max"]
        val = f"{lb}{lo}; {hi}{rb}"
    else:
        val = str(f["value"])
    return f"{name} = {val} {unit}".strip() if unit else f"{name} = {val}"


def _survivors(candidates, facts, known):
    left = candidates
    for f in facts:
        left = narrow(left, f, known)
        if not left:
            break
    return left


def _minimal_conflicts(candidates, facts, known, max_size=3):
    """Минимальные наборы фактов (индексы), которые вместе дают 0 позиций."""
    found = []
    for k in range(1, min(max_size, len(facts)) + 1):
        for subset in combinations(range(len(facts)), k):
            if any(set(c) <= set(subset) for c in found):
                continue
            if not _survivors(candidates, [facts[i] for i in subset], known):
                found.append(subset)
    return found


def _distance(fact, opt_fact):
    """Насколько вариант opt_fact далёк от числового факта (для выбора ближайшего)."""
    if fact["type"] != "number":
        return 0
    x = fact["value"]
    if opt_fact["type"] == "number":
        return abs(opt_fact["value"] - x)
    if opt_fact["type"] == "interval":
        lo, hi = opt_fact["value"]["min"], opt_fact["value"]["max"]
        if lo is not None and x < lo:
            return lo - x
        if hi is not None and x > hi:
            return x - hi
    return 0


def _alternatives(pool, f, known, limit=8):
    """Допустимые значения характеристики f в pool + сколько позиций останется."""
    opts = _options(pool, f["name"])
    for o in opts:
        o["remaining"] = len(narrow(pool, o["fact"], known))
    opts = [o for o in opts if o["remaining"] > 0]
    opts.sort(key=lambda o: (_distance(f, o["fact"]), -o["remaining"]))
    return opts[:limit]


# ---------- одиночная причина ----------

def _single_reason(candidates, f, known):
    """Почему ОДИН факт сам даёт 0 позиций. Возвращает (kind, message, suggestions)."""
    name = f["name"]
    opts = _options(candidates, name)

    if not opts:
        close = get_close_matches(name, sorted(known), n=3, cutoff=0.6)
        msg = f"Ни у одной подходящей позиции нет характеристики «{name}»."
        if close:
            msg += " Возможно, вы имели в виду: " + ", ".join(f"«{c}»" for c in close) + "."
        return "unknown_characteristic", msg, close

    numeric = [o for o in opts if o["fact"]["type"] in ("number", "interval")]

    if f["type"] == "string":
        labels = [o["label"] for o in opts]
        close = get_close_matches(str(f["value"]), labels, n=1, cutoff=0.6)
        msg = f"Значение «{f['value']}» для «{name}» не встречается в КТРУ."
        if close:
            msg += f" Возможно, вы имели в виду «{close[0]}»?"
        return "value_not_allowed", msg, close

    if not numeric:
        return ("value_not_allowed",
                f"Для «{name}» допустимы только текстовые значения, а указано число.", [])

    units = sorted({o["fact"].get("unit") for o in numeric if o["fact"].get("unit")})
    if f.get("unit") and f["unit"] not in units:
        return ("unit_mismatch",
                f"Единица «{f['unit']}» не подходит для «{name}». Допустимые единицы: {', '.join(units)}.",
                units)

    return ("out_of_range",
            f"Значение {_fmt_fact(f)} не входит ни в один допустимый вариант.", [])


# ---------- публичные функции ----------

def make_conflict_hints(candidates, facts, known):
    """Подсказки при status == "conflict". Пустой список, если конфликта нет."""
    if not candidates:
        return [{"kind": "no_candidates", "facts": [],
                 "message": "Не найдено ни одной позиции по описанию товара.",
                 "options": []}]
    if not facts or _survivors(candidates, facts, known):
        return []

    hints = []
    for subset in _minimal_conflicts(candidates, facts, known):
        fs = [facts[i] for i in subset]

        # Для каждого факта из конфликта: что будет, если его убрать или заменить.
        fixes = []
        for f in fs:
            others = [g for g in facts if g is not f]
            base = _survivors(candidates, others, known)
            fix = {"fact": f, "label": _fmt_fact(f),
                   "drop": {"remaining": len(base)},
                   "options": _alternatives(base, f, known) if base else [],
                   "blocked_by_other_conflict": not base}
            fixes.append(fix)

        if len(fs) == 1:
            kind, msg, suggestions = _single_reason(candidates, fs[0], known)
            hints.append({"kind": kind, "facts": fs, "message": msg,
                          "suggestions": suggestions, "fixes": fixes})
        else:
            names = " и ".join(f"«{_fmt_fact(f)}»" for f in fs)
            hints.append({"kind": "conflict", "facts": fs,
                          "message": f"{names} по отдельности подходят, но вместе не подходят ни к одной позиции. "
                                     "Уберите или измените одно из них.",
                          "suggestions": [], "fixes": fixes})

    if not hints:  # конфликт возникает только на 4+ фактах одновременно
        hints.append({"kind": "conflict", "facts": list(facts),
                      "message": "Заданные характеристики вместе не подходят ни к одной позиции.",
                      "suggestions": [], "fixes": []})
    return hints


def _signature(p):
    return json.dumps({n: c.get("values") for n, c in sorted(p["chars"].items())},
                      sort_keys=True, ensure_ascii=False, default=str)


def make_indistinguishable_hint(left, facts, known, hints):
    """Для ambiguous: если make_hints ничего не предложил, а позиций несколько,
    значит оставшиеся позиции нельзя различить по характеристикам."""
    if len(left) < 2 or hints:
        return []
    groups = {}
    for p in left:
        groups.setdefault(_signature(p), []).append(p)
    same = len(groups) == 1
    codes = [p["code"] for p in left]
    msg = (f"Осталось {len(left)} позиций, и по характеристикам они не различаются: "
           f"{', '.join(codes)}. Подойдёт любая; различия, скорее всего, в названии или ОКПД2."
           if same else
           f"Осталось {len(left)} позиций, но ни одна из неиспользованных характеристик их не разделяет: "
           f"{', '.join(codes)}.")
    return [{"kind": "indistinguishable", "candidates": codes, "message": msg}]
