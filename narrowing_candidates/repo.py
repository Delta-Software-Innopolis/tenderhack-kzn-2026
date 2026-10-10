import sqlite3


def to_value(r):
    if r["quality_description"] is not None:
        return {"kind": "text", "text": r["quality_description"]}
    if r["concrete_value"] is not None:
        return {"kind": "number", "value": r["concrete_value"], "unit": r["okei_name"]}
    if r["min_value"] is None and r["max_value"] is None:
        return None   # пустая строка без данных, пропускаем
    return {
        "kind": "range",
        "unit": r["okei_name"],
        "lo": r["min_value"],
        "lo_incl": r["min_notation"] == "greaterOrEqual",
        "hi": r["max_value"],
        "hi_incl": r["max_notation"] == "lessOrEqual",
    }


def load_positions(db_path, name_like=None, codes=None):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    positions = {}
    for r in db.execute(
        "SELECT code, name FROM ktru_position WHERE status = 'ACTIVE'"
    ):
        if codes is not None and r["code"] not in codes:
            continue
        if name_like and name_like.lower() not in (r["name"] or "").lower():
            continue
        positions[r["code"]] = {"code": r["code"], "name": r["name"], "chars": {}}

    chars_by_id = {}
    for r in db.execute(
        "SELECT id, position_code, name, type, is_required FROM ktru_characteristic"
    ):
        p = positions.get(r["position_code"])
        if p is None:
            continue
        ch = p["chars"].setdefault(
            r["name"],
            {"type": r["type"], "required": bool(r["is_required"]), "values": []},
        )
        chars_by_id[r["id"]] = ch

    for r in db.execute("SELECT * FROM ktru_characteristic_value"):
        ch = chars_by_id.get(r["characteristic_id"])
        if ch is None:
            continue
        v = to_value(r)
        if v is not None:
            ch["values"].append(v)

    return list(positions.values())
