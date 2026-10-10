import sqlite3
from repo import load_positions
from analyze import analyze

DB = "../ktru.db"

db = sqlite3.connect(DB)
templates = {r[0] for r in db.execute("SELECT code FROM ktru_position WHERE is_template = 1")}

hammers = [p for p in load_positions(DB) if "молоток" in (p["name"] or "").lower()]

print("Позиции молотка:")
for p in sorted(hammers, key=lambda p: p["code"]):
    types = [v["text"] for v in p["chars"].get("Тип", {"values": []})["values"]]
    mark = "ШАБЛОН" if p["code"] in templates else "      "
    print(" ", p["code"], mark, "| типов:", len(types), "|", types[:3])

print("\nПосле «Тип: Столярный»:")
r = analyze(hammers, [{"name": "Тип", "type": "string", "value": "Столярный"}])
for code in r["candidates"]:
    p = next(x for x in hammers if x["code"] == code)
    print(" ", code, "ШАБЛОН" if code in templates else "      ",
          {name: len(ch["values"]) for name, ch in p["chars"].items()})
