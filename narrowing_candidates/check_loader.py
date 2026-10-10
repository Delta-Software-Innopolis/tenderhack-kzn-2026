from collections import Counter
from repo import load_positions

DB = "../ktru.db"   # твой путь к базе

hammers = load_positions(DB, name_like="молоток")
print("Позиций молотка:", len(hammers))
print("Коды:", sorted(p["code"] for p in hammers))

p = hammers[0]
print("\nПример позиции:", p["code"], p["name"])
for name, ch in p["chars"].items():
    kinds = Counter(v["kind"] for v in ch["values"])
    print(f'  {name} (type={ch["type"]}, обязательная={ch["required"]}): {dict(kinds)}')

mass = p["chars"].get("Масса молотка")
if mass:
    print("\nИнтервалы массы:")
    for v in mass["values"][:4]:
        print("  ", v)

everything = load_positions(DB)
print("\nВсего активных позиций:", len(everything))
