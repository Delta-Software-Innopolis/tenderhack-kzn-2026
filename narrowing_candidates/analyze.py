from narrow import known_chars
from funnel import run_funnel
from hints import make_hints


def analyze(candidates, facts):
    known = known_chars(candidates)   # считаем до сужения
    funnel, left = run_funnel(candidates, facts, known)

    if len(left) == 1:
        status = "resolved"
        result_code = left[0]["code"]
    elif len(left) == 0:
        status = "conflict"
        result_code = None
    else:
        status = "ambiguous"
        result_code = None

    culprit = None
    if status == "conflict":
        for step in funnel:
            if step["before"] > 0 and step["after"] == 0:
                culprit = step["step"]
                break

    hints = make_hints(left, facts, known) if status == "ambiguous" else []

    return {
        "funnel": funnel,
        "candidates": [p["code"] for p in left],
        "status": status,
        "result_code": result_code,
        "culprit": culprit,
        "hints": hints,
    }
