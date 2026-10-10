"""Populate SQLite with multilingual-e5-small embeddings."""

from __future__ import annotations

import argparse
import sqlite3

from search import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_VERSION,
    ensure_search_schema,
    populate_embeddings,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calculate and store embeddings for indexed KTRU positions"
    )
    parser.add_argument("--db", default="ktru.db")
    parser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--version", default=DEFAULT_EMBEDDING_VERSION)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        ensure_search_schema(conn)
        count = populate_embeddings(
            conn,
            model_name=args.model,
            model_version=args.version,
            batch_size=args.batch_size,
            force=args.force,
        )
    finally:
        conn.close()
    print(f"Сохранено эмбеддингов: {count}")


if __name__ == "__main__":
    main()
