from positions import POSITIONS
from narrow import known_chars
from analyze import analyze

known = known_chars(POSITIONS)

scenarios = {
    "1) только масса 0.4-0.6": [("Масса молотка", "0.4-0.6")],
    "2) только безынерционный Да": [("Безынерционный", "Да")],
    "3) масса 0.4-0.6 + безынерционный Да": [
        ("Масса молотка", "0.4-0.6"),
        ("Безынерционный", "Да"),
    ],
}

for name, facts in scenarios.items():
    r = analyze(POSITIONS, facts, known)
    print(name)
    print("   осталось:", r["candidates"])
    if not r["hints"]:
        print("   подсказок нет")
    for h in r["hints"]:
        print(f'   {h["char"]} (в среднем останется {h["avg"]})')
        for o in h["options"]:
            print(f'      {o["value"]} -> {o["remaining"]}')
