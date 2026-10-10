from repo import load_positions
from analyze import analyze

DB = "../ktru.db"   # твой путь

ALL = {p["code"]: p for p in load_positions(DB)}   # один раз при запуске
hammers = [p for p in ALL.values() if "молоток" in (p["name"] or "").lower()]
print("Кандидатов:", len(hammers))


def show(title, facts):
    r = analyze(hammers, facts)
    print("\n==", title)
    for s in r["funnel"]:
        print("  ", s["step"], s["before"], "->", s["after"])
    print("   статус:", r["status"], "| код:", r["result_code"],
          "| осталось:", len(r["candidates"]), "| виновник:", r["culprit"])
    for h in r["hints"][:3]:
        print("   подсказка:", h["name"], "(обязательная)" if h["required"] else "")
        for o in h["options"][:6]:
            print("      ", o["label"], "->", o["remaining"])


show("1. без фактов", [])

show("2. масса 0.5 кг", [
    {"name": "Масса молотка", "type": "number", "value": 0.5, "unit": "Килограмм"},
])

show("3. масса 0.5 кг + безынерционный", [
    {"name": "Масса молотка", "type": "number", "value": 0.5, "unit": "Килограмм"},
    {"name": "Безынерционный", "type": "string", "value": "Да"},
])

show("4. интервал массы 0.4-0.8 кг", [
    {"name": "Масса молотка", "type": "interval", "unit": "Килограмм",
     "value": {"min": 0.4, "max": 0.8, "min_inclusive": True, "max_inclusive": False}},
])

show("5. тип: столярный", [
    {"name": "Тип", "type": "string", "value": "Столярный"},
])

show("6. неадекватная характеристика", [
    {"name": "Количество ножек", "type": "number", "value": 4, "unit": "Штука"},
])
