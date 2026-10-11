import sqlite3
from search import canonicalize_query, encode_query, semantic_search_scored

conn = sqlite3.connect("file:ktru.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

GOOD = ["молоток слесарный", "стол офисный", "перчатки рабочие", "стул", "куртка зимняя"]
BAD = ["asdfgh", "квантовый борщ", "ноутбук", "картофель", "рыба на луне"]

for label, queries in (("GOOD", GOOD), ("BAD", BAD)):
    print(label)
    for q in queries:
        emb = encode_query(canonicalize_query(conn, q))
        hits = semantic_search_scored(
            conn, emb, limit=5, min_score=-1.0, margin=float("inf"))
        print(f"  {q!r:28}", [round(s, 3) for _, s in hits])
