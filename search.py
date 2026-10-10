"""Поиск кода КТРУ по текстовому запросу.

Запуск:  python search.py "кухонный стол" [-n 5] [--all] [--db ktru.db]
По умолчанию ищет только среди позиций со статусом ACTIVE.
"""
import argparse
import sqlite3

from textutil import lemmas


def search(conn, query: str, limit: int = 5, only_active: bool = True):
    words = lemmas(query)
    if not words:
        return []
    # Сначала строгий поиск (все слова обязательны), если пусто — мягкий (любое слово).
    for joiner in (" AND ", " OR "):
        match = joiner.join(f'"{w}"' for w in dict.fromkeys(words))
        rows = conn.execute(
            f"""SELECT p.code, p.name, p.status, p.okpd2_code,
                       bm25(ktru_fts, 10.0, 3.0, 1.0) AS score
                FROM ktru_fts
                JOIN ktru_position p ON p.rowid = ktru_fts.rowid
                WHERE ktru_fts MATCH ?
                  {"AND p.status = 'ACTIVE'" if only_active else ""}
                ORDER BY score
                LIMIT ?""",
            (match, limit),
        ).fetchall()
        if rows:
            return rows
    return []


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("-n", type=int, default=5)
    ap.add_argument("--all", action="store_true", help="включая неактивные позиции")
    ap.add_argument("--db", default="ktru.db")
    a = ap.parse_args()

    conn = sqlite3.connect(a.db)
    results = search(conn, a.query, a.n, only_active=not a.all)
    if not results:
        print("ничего не найдено")
    for code, name, status, okpd2, score in results:
        print(f"{code}  [{status}]  {name}  (ОКПД2 {okpd2}, score {score:.2f})")
