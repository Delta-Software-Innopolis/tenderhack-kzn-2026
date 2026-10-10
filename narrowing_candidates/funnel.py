from narrow import narrow

def describe(fact):
    unit = f' {fact["unit"]}' if fact.get("unit") else ""
    v = fact["value"]
    if fact["type"] == "interval":
        lo = "" if v.get("min") is None else v["min"]
        hi = "" if v.get("max") is None else v["max"]
        lb = "[" if v.get("min_inclusive", True) else "("
        rb = "]" if v.get("max_inclusive", False) else ")"
        v = f"{lb}{lo}; {hi}{rb}"
    return f'{fact["name"]}: {v}{unit}'


def run_funnel(candidates, facts, known):
    left = candidates
    funnel = []

    for fact in facts:
        before = len(left)
        left = narrow(left, fact, known)
        funnel.append({
            "step": describe(fact),
            "before": before,
            "after": len(left),
        })

    return funnel, left
