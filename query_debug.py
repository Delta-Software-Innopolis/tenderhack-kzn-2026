"""Interactive inspection of KTRU query transformations and search results."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from search import (
    DEFAULT_EMBEDDING_MODEL,
    _fts_query,
    bm25_search,
    canonicalize_query,
    encode_query,
    lemmatize,
    search,
    semantic_search,
    tokenize_with_offsets,
)


def run_query(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    with_embedding: bool = True,
) -> dict:
    canonical = canonicalize_query(conn, query)
    result = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "canonical_query": canonical,
        "lemmatized_query": lemmatize(canonical, remove_stop_words=True),
        "fts_query": _fts_query(canonical),
        "tokens": [token.__dict__ for token in tokenize_with_offsets(query)],
        "bm25_codes": bm25_search(conn, query, limit=50),
        "bm25_results": search(conn, query, limit=limit),
        "embedding": {
            "available": False,
            "model": DEFAULT_EMBEDDING_MODEL,
            "values": None,
            "semantic_codes": [],
            "error": None,
        },
    }

    if not with_embedding:
        result["embedding"]["error"] = "Отключено параметром --no-embedding"
    else:
        try:
            vector = encode_query(query)
        except RuntimeError as exc:
            result["embedding"]["error"] = str(exc)
        else:
            result["embedding"]["available"] = True
            result["embedding"]["values"] = vector.tolist()
            result["embedding"]["semantic_codes"] = semantic_search(
                conn, vector, limit=50
            )
            result["hybrid_results"] = search(
                conn,
                query,
                limit=limit,
                query_embedding=vector,
            )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactively inspect KTRU query processing"
    )
    parser.add_argument("--db", default="ktru.db")
    parser.add_argument("--output", default="query_debug.json")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--no-embedding",
        action="store_true",
        help="не загружать модель и сохранить только BM25-трассировку",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    output = Path(args.output)
    try:
        print("Введите query. Пустая строка завершает программу.")
        while True:
            query = input("\nquery> ").strip()
            if not query:
                break

            result = run_query(conn, query, args.limit, not args.no_embedding)
            output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"Результат сохранён в {output}")
            print(f"Канонический запрос: {result['canonical_query']}")
            print(f"Леммы: {result['lemmatized_query']}")
            print(f"BM25-кандидатов: {len(result['bm25_results'])}")
            if result["embedding"]["available"]:
                print("Эмбеддинг: рассчитан")
                print(f"Hybrid-кандидатов: {len(result['hybrid_results'])}")
            else:
                print(f"Эмбеддинг: недоступен ({result['embedding']['error']})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
