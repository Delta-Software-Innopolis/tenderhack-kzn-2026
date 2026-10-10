import sqlite3
import unittest
from pathlib import Path

from search import (
    CANONICAL_ALIASES,
    bm25_search,
    canonicalize_query,
    validate_canonical_aliases,
)


DB_PATH = Path(__file__).with_name("ktru.db")


class SearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = sqlite3.connect(DB_PATH)
        cls.conn.row_factory = sqlite3.Row

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_all_aliases_resolve_to_existing_ktru_names(self):
        aliases = validate_canonical_aliases(self.conn)
        self.assertEqual(aliases, CANONICAL_ALIASES)

    def test_alias_is_rewritten_to_canonical_name(self):
        query = canonicalize_query(self.conn, "нужна больничная койка")
        self.assertIn("Кровать больничная", query)
        self.assertNotIn("больничная койка", query)

    def test_canonical_alias_returns_bm25_candidates(self):
        codes = bm25_search(self.conn, "больничная койка")
        self.assertTrue(codes)

        placeholders = ",".join("?" for _ in codes)
        names = self.conn.execute(
            f"SELECT DISTINCT name FROM ktru_position WHERE code IN ({placeholders})",
            codes,
        ).fetchall()
        self.assertIn("Кровать больничная", {row["name"] for row in names})


if __name__ == "__main__":
    unittest.main()
