from narrow import narrow


def _with_unit(text, unit):
    return f"{text} {unit}" if unit else text


def _fmt_interval(v):
    lb = "[" if v["lo_incl"] else "("
    rb = "]" if v["hi_incl"] else ")"
    lo = "-∞" if v["lo"] is None else v["lo"]
    hi = "∞" if v["hi"] is None else v["hi"]
    return f"{lb}{lo}; {hi}{rb}"


def _options(candidates, name):
    """Уникальные допустимые значения характеристики у оставшихся позиций.
    К каждому приложен готовый факт, который можно отправить обратно в движок."""
    seen = {}
    for p in candidates:
        ch = p["chars"].get(name)
        if ch is None:
            continue
        for v in ch["values"]:
            if v["kind"] == "text":
                key = ("text", v["text"])
                label = v["text"]
                fact = {"name": name, "type": "string", "value": v["text"]}
            elif v["kind"] == "number":
                key = ("number", v["value"], v["unit"])
                label = _with_unit(str(v["value"]), v["unit"])
                fact = {"name": name, "type": "number", "value": v["value"], "unit": v["unit"]}
            else:
                key = ("range", v["lo"], v["lo_incl"], v["hi"], v["hi_incl"], v["unit"])
                label = _with_unit(_fmt_interval(v), v["unit"])
                fact = {"name": name, "type": "interval", "unit": v["unit"],
                        "value": {"min": v["lo"], "max": v["hi"],
                                  "min_inclusive": v["lo_incl"], "max_inclusive": v["hi_incl"]}}
            if key not in seen:
                seen[key] = {"label": label, "fact": fact}
    return list(seen.values())


def make_hints(candidates, facts, known):
    used = {f["name"] for f in facts}
    hints = []

    for name in sorted(known - used):
        options = _options(candidates, name)
        if not options:
            continue

        for o in options:
            o["remaining"] = len(narrow(candidates, o["fact"], known))

        # ни один вариант ничего не отсекает: подсказка бесполезна
        if min(o["remaining"] for o in options) == len(candidates):
            continue

        avg = sum(o["remaining"] for o in options) / len(options)
        required = any(p["chars"].get(name, {}).get("required") for p in candidates)
        hints.append({"name": name, "required": bool(required),
                      "avg": round(avg, 2), "options": options})

    hints.sort(key=lambda h: (not h["required"], h["avg"]))
    return hints
