"""Extract query characteristics and compare ONLY the supplied KTRU candidates.

Run independently: uv run python chars_extractor.py QUERY CODE [CODE ...]
Import from the repository: from chars_extractor import extract_characteristics
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path

if __package__:
    from .language import canonical, extract, name_key, STOP, TOKEN
    from .values import compare_numeric, from_db
    from .normalization import normalize_characteristic
    from .catalog import coalesce_characteristics, source_ids
else:
    from language import canonical, extract, name_key, STOP, TOKEN
    from values import compare_numeric, from_db
    from normalization import normalize_characteristic
    from catalog import coalesce_characteristics, source_ids


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "ktru.db"


def _load_candidates(db_path: Path, codes: list[str]):
    if not codes:
        return [], []
    candidates, by_id = {}, {}
    # mode=ro fails for a missing database instead of accidentally creating one.
    with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")  # One consistent snapshot for all three reads.
        for offset in range(0, len(codes), 400):
            batch = codes[offset:offset + 400]
            parameters = ",".join("?" for _ in batch)
            for row in conn.execute(
                f"SELECT code, name FROM ktru_position WHERE code IN ({parameters})", batch,
            ):
                candidates[row["code"]] = {**dict(row), "characteristics": []}
            for row in conn.execute(
                f"""SELECT id, position_code, code, name, type, kind, is_required, choice_type
                    FROM ktru_characteristic WHERE position_code IN ({parameters}) ORDER BY id""", batch,
            ):
                characteristic = dict(row)
                code = characteristic.pop("position_code")
                characteristic["ktru_type"] = characteristic.pop("type")
                characteristic.update(values=[], issues=[])
                by_id[row["id"]] = characteristic
                candidates[code]["characteristics"].append(characteristic)
            for row in conn.execute(
                f"""SELECT v.* FROM ktru_characteristic_value v
                    JOIN ktru_characteristic c ON c.id = v.characteristic_id
                    WHERE c.position_code IN ({parameters}) ORDER BY v.id""", batch,
            ):
                characteristic = by_id[row["characteristic_id"]]
                try:
                    characteristic["values"].extend(from_db(characteristic["name"], dict(row)))
                except ValueError as error:
                    characteristic["issues"].append({"value_id": row["id"], "reason": str(error)})
    for candidate in candidates.values():
        candidate['characteristics'] = coalesce_characteristics(candidate['characteristics'])
    return [candidates[c] for c in codes if c in candidates], [c for c in codes if c not in candidates]


@lru_cache(maxsize=1)
def _semantic_model(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise RuntimeError("Для семантического режима выполните uv sync --extra semantic в chars_extractor") from error
    return SentenceTransformer(model_name)


def _find_characteristics(query_char, definitions, semantic_model, threshold, margin):
    hints = query_char.get("possible_names")
    if hints:
        return [c for c in definitions if c["name"] in hints], "value_context"
    key = name_key(query_char["name"])
    exact = [c for c in definitions if name_key(c["name"]) == key]
    if exact:
        return exact, "name"
    # An unqualified name is only usable if it identifies one characteristic.
    partial = [c for c in definitions if set(key) < set(name_key(c["name"]))]
    if key and partial:
        # Preserve qualifier relationships: "основное сырьё" is different from
        # "дополнительное сырьё ... основного материала" despite shared words.
        phrase = canonical(query_char['name'])
        adjacent = [c for c in partial if any(canonical(c['name'])[i:i + len(phrase)] == phrase
                    for i in range(len(canonical(c['name'])) - len(phrase) + 1))]
        if len(phrase) > 1 and adjacent:
            partial = adjacent
        return partial, "short_name"
    if not semantic_model or not definitions:
        return [], "name"
    model = _semantic_model(semantic_model)
    query_vector = model.encode_query([query_char["name"]], normalize_embeddings=True)
    name_vectors = model.encode_document([c["name"] for c in definitions], normalize_embeddings=True)
    scores = (query_vector @ name_vectors.T)[0].tolist()
    ranked = sorted(zip(scores, definitions), key=lambda pair: pair[0], reverse=True)
    if ranked[0][0] < threshold:
        return [], "semantic"
    return [c for score, c in ranked if score >= threshold and ranked[0][0] - score < margin], "semantic"


def _compare(query_char: dict, characteristic: dict):
    allowed = characteristic["values"]
    if characteristic["issues"]:
        return {"status": "not_comparable", "reason": "Некорректные значения в исходных данных КТРУ"}
    if not allowed:
        return {"status": "not_comparable", "reason": "В КТРУ нет допустимых значений"}
    if query_char["type"] in ("number", "interval"):
        return compare_numeric(query_char, allowed)
    strings = [value for value in allowed if value["type"] == "string"]
    key = canonical(query_char["value"])
    if not strings:
        return {"status": "value_mismatch", "reason": "В КТРУ нет строковых значений"}
    equal = [canonical(value["value"]) == key for value in strings]
    matches = any(not item for item in equal) if query_char.get("negated") else any(equal)
    return {"status": "matched" if matches else "value_mismatch"}


def _unrecognized(query: str, candidates: list[dict], occupied: set[int]):
    # Do not report the product's own name or ordinary connecting words as attributes.
    product_words = {word for candidate in candidates for word in canonical(candidate["name"])}
    ignored = product_words | STOP | {"нужный", "нужен", "нужно", "требоваться", "купить", "товар"}
    fragments, start, end = [], None, None
    for token in TOKEN.finditer(query):
        key = canonical(token.group())
        relevant = key and not set(key) <= ignored and not any(p in occupied for p in range(token.start(), token.end()))
        if relevant:
            if start is None:
                start = token.start()
            end = token.end()
        elif start is not None:
            fragments.append({"source": query[start:end], "start": start, "end": end,
                              "reason": "Фрагмент не сопоставлен с характеристикой"})
            start = end = None
    if start is not None:
        fragments.append({"source": query[start:end], "start": start, "end": end,
                          "reason": "Фрагмент не сопоставлен с характеристикой"})
    return fragments


def extract_characteristics(
    normalized_query: str,
    candidate_codes: list[str],
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    semantic_model: str | None = None,
    semantic_threshold: float = 0.8,
    semantic_margin: float = 0.05,
) -> dict:
    """Normalize requested characteristics and select compatible supplied candidates.

    Query spans refer to the supplied normalized text, not the original user input.
    Range matching requires FULL coverage by the union of the candidate's allowed
    values. Mere intersection is reported as partial_match. Unitless numbers inherit
    a unit only when all numeric alternatives of that characteristic use one unit.

    Neural name matching is opt-in. Its thresholds need calibration on your queries;
    the scores are not probabilities. Neither mode invents missing KTRU attributes.
    """
    if not isinstance(normalized_query, str):
        raise TypeError("normalized_query должен быть строкой")
    if not isinstance(candidate_codes, (list, tuple)) or any(not isinstance(c, str) or not c.strip() for c in candidate_codes):
        raise TypeError("candidate_codes должен быть списком непустых строк с кодами КТРУ")
    if not 0 <= semantic_threshold <= 1 or not 0 < semantic_margin <= 1:
        raise ValueError("Порог должен быть от 0 до 1, margin — больше 0 и не больше 1")
    codes = list(dict.fromkeys(candidate_codes))
    candidates, unknown_codes = _load_candidates(Path(db_path), codes)
    definitions = [c for candidate in candidates for c in candidate["characteristics"]]
    query_chars, issues, occupied = extract(normalized_query, definitions, [c['name'] for c in candidates])
    unrecognized = sorted(issues + _unrecognized(normalized_query, candidates, occupied), key=lambda f: f["start"])
    normalized_chars = []
    for query_char in query_chars:
        options, _ = _find_characteristics(query_char, definitions, semantic_model, semantic_threshold, semantic_margin)
        normalized_chars.append(normalize_characteristic(query_char, options, candidates))
    selected, rejected = [], []
    for candidate in candidates:
        matches = []
        for index, query_char in enumerate(query_chars):
            options, method = _find_characteristics(
                query_char, candidate["characteristics"], semantic_model, semantic_threshold, semantic_margin,
            )
            match = {"query_index": index, "method": method}
            if not options:
                match.update(status="not_found", reason="Характеристика не найдена у кандидата")
            elif len(options) > 1 and query_char.get('match_mode') == 'any':
                comparisons = [(c, _compare(query_char, c)) for c in options]
                matching = [c for c, result in comparisons if result['status'] == 'matched']
                match.update(match_mode='any', characteristic_ids=[i for c in options for i in source_ids(c)],
                             matched_characteristic_ids=[i for c in matching for i in source_ids(c)])
                if matching:
                    match.update(status='matched', reason='Значение допустимо хотя бы в одной из указанных характеристик')
                elif any(result['status'] in {'not_comparable', 'ambiguous'} for _, result in comparisons):
                    match.update(status='not_comparable', reason='Не удалось проверить все альтернативные характеристики')
                else:
                    match.update(status='value_mismatch', reason='Значение не подходит ни к одной из альтернативных характеристик')
            elif len(options) > 1:
                match.update(status="ambiguous", characteristic_ids=[i for c in options for i in source_ids(c)],
                             reason="Подходит несколько характеристик; требуется уточнение")
            else:
                characteristic = options[0]
                match.update(characteristic_id=characteristic["id"], name=characteristic["name"],
                             **_compare(query_char, characteristic))
                if len(source_ids(characteristic)) > 1:
                    match['characteristic_ids'] = source_ids(characteristic)
            matches.append(match)
        states = {match["status"] for match in matches}
        if states & {"value_mismatch", "unit_mismatch"}:
            status = "mismatch"
        elif unrecognized or states & {"not_found", "ambiguous", "not_comparable"}:
            status = "partial_match" if states & {"matched", "partial_match"} else "undetermined"
        elif "partial_match" in states:
            status = "partial_match"
        elif matches:
            status = "matched"
        else:
            status = "no_constraints"
        candidate.update(matches=matches, status=status)
        if status in {'matched', 'partial_match', 'no_constraints'}:
            selected.append(candidate)
        else:
            rejected.append({key: candidate[key] for key in ('code', 'name', 'matches', 'status')})
    return {"query": normalized_query, "chars": normalized_chars, "candidates": selected,
            "rejected_candidates": rejected,
            "unknown_candidate_codes": unknown_codes, "unrecognized": unrecognized}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Нормализованный запрос с сохранёнными операторами и диапазонами")
    parser.add_argument("codes", nargs="+", help="Коды кандидатов КТРУ")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--semantic-model", help="Необязательная модель Sentence Transformers или путь к ней")
    args = parser.parse_args()
    result = extract_characteristics(args.query, args.codes, db_path=args.db, semantic_model=args.semantic_model)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
