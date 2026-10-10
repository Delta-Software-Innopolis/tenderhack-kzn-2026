"""Общая нормализация текста: и загрузчик, и поиск должны лемматизировать одинаково."""
import re
from functools import lru_cache
 
import pymorphy3
 
_morph = pymorphy3.MorphAnalyzer()
# Число (с десятичной точкой/запятой) или слово. "20см" -> "20", "см".
_TOKEN = re.compile(r"\d+(?:[.,]\d+)?|[а-яёa-z]+")
 
# Частые сокращения единиц -> полное название, как в ОКЕИ ("Сантиметр", "Килограмм").
_UNITS = {
    "мм": "миллиметр", "см": "сантиметр", "дм": "дециметр", "м": "метр", "км": "километр",
    "мг": "миллиграмм", "г": "грамм", "гр": "грамм", "кг": "килограмм", "т": "тонна",
    "мл": "миллилитр", "л": "литр", "шт": "штука", "уп": "упаковка",
    "вт": "ватт", "квт": "киловатт", "в": "вольт", "а": "ампер",
}
 
 
@lru_cache(maxsize=200_000)
def _lemma(word: str) -> str:
    return _morph.parse(word)[0].normal_form
 
 
def lemmas(text: str | None) -> list[str]:
    if not text:
        return []
    out = []
    for w in _TOKEN.findall(text.lower().replace("ё", "е")):
        if w[0].isdigit():
            out.append(w.replace(",", "."))
        else:
            out.append(_lemma(_UNITS.get(w, w)))
    return out
 
 
def lemma_string(*texts: str | None) -> str:
    return " ".join(w for t in texts for w in lemmas(t))
 
