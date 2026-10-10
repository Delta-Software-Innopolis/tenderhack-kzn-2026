"""Hybrid lexical/semantic search over KTRU positions."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date

import pymorphy3

try:
    import numpy as np
except ImportError:  # Semantic search is optional until embeddings are installed.
    np = None

STOP_WORDS = frozenset(
    "и в на с по для из к о от до не ни но а или что как это тот весь свой".split()
)
# Values must be copied from ktru_position.name, not invented generic labels.
# Add a user expression only when the target exists in the loaded KTRU database.
CANONICAL_ALIASES = {
    "больничная койка": "Кровать больничная",
    "медицинская кровать": "Кровать больничная",
    "детская кроватка": "Кровать педиатрическая",
    "операционный стол": "Стол операционный универсальный",
    "хирургический стол": "Стол операционный универсальный",
    "рабочая одежда": (
        "Одежда специальная для защиты от общих производственных загрязнений "
        "и механических воздействий"
    ),
}
TOKEN_RE = re.compile(r"\S+")
DECIMAL_COMMA_RE = re.compile(r"(\d),(\d{1,2})(?!\d)")
THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d{3}\b)")
_MORPH = pymorphy3.MorphAnalyzer()
DEFAULT_EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
DEFAULT_EMBEDDING_VERSION = "1"
BM25_CANDIDATE_LIMIT = 50
BM25_MIN_STRICT_RESULTS = 10


@dataclass(frozen=True)
class Token:
    raw: str
    normalized: str
    start: int
    end: int


def normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = DECIMAL_COMMA_RE.sub(r"\1.\2", text)
    text = THOUSANDS_RE.sub("", text)
    return text.replace(",", " ")


def normalize_token(token: str) -> str:
    token = token.lower().replace("ё", "е")
    token = DECIMAL_COMMA_RE.sub(r"\1.\2", token)
    token = token.strip(".,;:!?()[]{}\"'")
    return token.replace(",", "")


def tokenize_with_offsets(text: str) -> list[Token]:
    return [
        Token(match.group(), normalize_token(match.group()), match.start(), match.end())
        for match in TOKEN_RE.finditer(text)
        if normalize_token(match.group())
    ]


def _expand_synonyms(text: str, aliases: dict[str, str] | None = None) -> str:
    for source, target in (aliases or CANONICAL_ALIASES).items():
        text = re.sub(rf"\b{re.escape(source)}\b", target, text)
    return text


def lemmatize(
    text: str,
    remove_stop_words: bool = False,
    aliases: dict[str, str] | None = None,
) -> str:
    normalized = _expand_synonyms(normalize(text), aliases)
    lemmas = []
    for token in normalized.split():
        lemma = _MORPH.parse(token)[0].normal_form
        if not remove_stop_words or lemma not in STOP_WORDS:
            lemmas.append(lemma)
    return " ".join(lemmas)


def validate_canonical_aliases(
    conn: sqlite3.Connection,
    aliases: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return aliases whose targets are exact names in the KTRU database."""
    aliases = aliases or CANONICAL_ALIASES
    names = {
        row["name"]
        for row in conn.execute("SELECT DISTINCT name FROM ktru_position")
        if row["name"]
    }
    invalid = {source: target for source, target in aliases.items() if target not in names}
    if invalid:
        details = ", ".join(f"{source!r} -> {target!r}" for source, target in invalid.items())
        raise ValueError(f"Aliases point to names absent from KTRU: {details}")
    return dict(aliases)


def canonicalize_query(
    conn: sqlite3.Connection,
    query: str,
    aliases: dict[str, str] | None = None,
) -> str:
    """Replace user wording with exact KTRU names before lemmatization."""
    return _expand_synonyms(query, validate_canonical_aliases(conn, aliases))


def ensure_search_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ktru_position_search (
            position_code TEXT PRIMARY KEY,
            raw_text TEXT NOT NULL,
            normalized_text TEXT NOT NULL,
            lemmatized_text TEXT NOT NULL,
            tokens_json TEXT NOT NULL,
            FOREIGN KEY (position_code) REFERENCES ktru_position(code) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS ktru_position_embedding (
            position_code TEXT PRIMARY KEY,
            model_name TEXT NOT NULL,
            model_version TEXT NOT NULL,
            embedding BLOB NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (position_code) REFERENCES ktru_position(code) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_emb_model
            ON ktru_position_embedding(model_name, model_version);
        """
    )
    # The original project schema used this name for a title-only FTS table.
    # Replacing that index is safe: it is derived data and not user data.
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(ktru_position_fts)")
    }
    if columns != {"lemmatized_text"}:
        conn.execute("DROP TABLE IF EXISTS ktru_position_fts")
        conn.execute(
            """
            CREATE VIRTUAL TABLE ktru_position_fts USING fts5(
                lemmatized_text,
                content='ktru_position_search',
                content_rowid='rowid',
                tokenize='unicode61 remove_diacritics 2'
            )
            """
        )
    conn.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS ktru_search_ai
        AFTER INSERT ON ktru_position_search BEGIN
            INSERT INTO ktru_position_fts(rowid, lemmatized_text)
            VALUES (new.rowid, new.lemmatized_text);
        END;
        CREATE TRIGGER IF NOT EXISTS ktru_search_ad
        AFTER DELETE ON ktru_position_search BEGIN
            INSERT INTO ktru_position_fts(ktru_position_fts, rowid, lemmatized_text)
            VALUES ('delete', old.rowid, old.lemmatized_text);
        END;
        CREATE TRIGGER IF NOT EXISTS ktru_search_au
        AFTER UPDATE ON ktru_position_search BEGIN
            INSERT INTO ktru_position_fts(ktru_position_fts, rowid, lemmatized_text)
            VALUES ('delete', old.rowid, old.lemmatized_text);
            INSERT INTO ktru_position_fts(rowid, lemmatized_text)
            VALUES (new.rowid, new.lemmatized_text);
        END;
        """
    )
    conn.commit()


def _position_text(conn: sqlite3.Connection, code: str, name: str, okpd2_name: str | None) -> str:
    parts = [name, okpd2_name or "", code]
    for row in conn.execute(
        """
        SELECT c.name, v.quality_description, v.okei_name, v.min_value,
               v.max_value, v.concrete_value
        FROM ktru_characteristic c
        LEFT JOIN ktru_characteristic_value v ON v.characteristic_id = c.id
        WHERE c.position_code = ?
        """,
        (code,),
    ):
        parts.extend(str(value) for value in row if value is not None)
    parts.extend(
        f"{row['name'] or ''} {row['code'] or ''}"
        for row in conn.execute(
            "SELECT name, code FROM ktru_rubricator WHERE position_code = ?", (code,)
        )
    )
    return " ".join(part for part in parts if part).strip()


def rebuild_search_documents(conn: sqlite3.Connection) -> int:
    ensure_search_schema(conn)
    rows = conn.execute(
        "SELECT code, name, okpd2_name FROM ktru_position ORDER BY code"
    ).fetchall()
    conn.execute("DELETE FROM ktru_position_search")
    for row in rows:
        raw = _position_text(conn, row["code"], row["name"], row["okpd2_name"])
        normalized = normalize(raw)
        tokens = [token.__dict__ for token in tokenize_with_offsets(raw)]
        conn.execute(
            """
            INSERT INTO ktru_position_search
            (position_code, raw_text, normalized_text, lemmatized_text, tokens_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (row["code"], raw, normalized, lemmatize(raw, remove_stop_words=True),
             json.dumps(tokens, ensure_ascii=False)),
        )
    conn.execute("INSERT INTO ktru_position_fts(ktru_position_fts) VALUES ('rebuild')")
    conn.commit()
    return len(rows)


def _fts_query(query: str, operator: str = "AND") -> str:
    if operator not in {"AND", "OR"}:
        raise ValueError("FTS operator must be 'AND' or 'OR'")
    terms = [term for term in lemmatize(query, remove_stop_words=True).split() if term]
    escaped = [term.replace('"', '""') for term in terms]
    return f" {operator} ".join(f'"{term}"' for term in escaped)


def _active_clause(alias: str = "p") -> tuple[str, list[str]]:
    today = date.today().isoformat()
    return (
        f"{alias}.status = 'ACTIVE' AND {alias}.actual = 1 "
        f"AND ({alias}.application_date_start IS NULL OR {alias}.application_date_start <= ?) "
        f"AND ({alias}.application_date_end IS NULL OR {alias}.application_date_end >= ?)",
        [today, today],
    )


def _bm25_search_mode(
    conn: sqlite3.Connection,
    query: str,
    operator: str,
    limit: int,
) -> list[str]:
    match = _fts_query(query, operator)
    if not match:
        return []
    return [
        row["code"]
        for row in conn.execute(
            """
            SELECT s.position_code AS code
            FROM ktru_position_fts f
            JOIN ktru_position_search s ON s.rowid = f.rowid
            WHERE ktru_position_fts MATCH ?
            ORDER BY bm25(ktru_position_fts)
            LIMIT ?
            """,
            (match, limit),
        )
    ]


def _merge_ranked_codes(*ranked_lists: list[str], limit: int) -> list[str]:
    """Fuse ranked lists while preserving evidence from every search mode."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, code in enumerate(ranked, 1):
            scores[code] = scores.get(code, 0.0) + 1 / (60 + rank)
    return [
        code
        for code, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ][:limit]


def bm25_search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = BM25_CANDIDATE_LIMIT,
    min_strict_results: int = BM25_MIN_STRICT_RESULTS,
) -> list[str]:
    """Search with strict AND first, then broaden to OR if needed.

    The OR fallback is only used when the strict result set is smaller than
    ``min_strict_results``. Results from both passes are rank-fused, so exact
    matches retain their evidence while partial matches fill the candidate set.
    """
    canonical_query = canonicalize_query(conn, query)
    strict = _bm25_search_mode(conn, canonical_query, "AND", limit)
    if len(strict) >= min_strict_results or len(strict) >= limit:
        return strict[:limit]

    broad = _bm25_search_mode(conn, canonical_query, "OR", limit)
    return _merge_ranked_codes(strict, broad, limit=limit)


def semantic_search(
    conn: sqlite3.Connection, query_embedding, limit: int = 50
) -> list[str]:
    if np is None or query_embedding is None:
        return []
    rows = conn.execute(
        "SELECT position_code, embedding FROM ktru_position_embedding"
    ).fetchall()
    if not rows:
        return []
    codes = [row["position_code"] for row in rows]
    matrix = np.frombuffer(b"".join(row["embedding"] for row in rows), dtype=np.float32)
    matrix = matrix.reshape(len(rows), -1)
    vector = np.asarray(query_embedding, dtype=np.float32)
    vector /= max(float(np.linalg.norm(vector)), 1e-12)
    scores = matrix @ vector
    return [codes[index] for index in np.argsort(-scores)[:limit]]


def _load_embedding_model(model_name: str = DEFAULT_EMBEDDING_MODEL):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Для расчёта эмбеддингов установите sentence-transformers: "
            "python -m pip install sentence-transformers"
        ) from exc
    return SentenceTransformer(model_name)


def _embedding_text(text: str, kind: str) -> str:
    if kind not in {"query", "passage"}:
        raise ValueError("Embedding kind must be 'query' or 'passage'")
    return f"{kind}: {text}"


def populate_embeddings(
    conn: sqlite3.Connection,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    model_version: str = DEFAULT_EMBEDDING_VERSION,
    batch_size: int = 32,
    force: bool = False,
) -> int:
    """Encode indexed KTRU documents and persist normalized float32 vectors."""
    model = _load_embedding_model(model_name)
    rows = conn.execute(
        """
        SELECT s.position_code, s.normalized_text
        FROM ktru_position_search s
        LEFT JOIN ktru_position_embedding e ON e.position_code = s.position_code
            AND e.model_name = ? AND e.model_version = ?
        WHERE e.position_code IS NULL OR ? = 1
        ORDER BY s.position_code
        """,
        (model_name, model_version, int(force)),
    ).fetchall()
    if not rows:
        return 0

    texts = [_embedding_text(row["normalized_text"], "passage") for row in rows]
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.ndim != 2 or len(vectors) != len(rows):
        raise RuntimeError("Модель вернула эмбеддинги неожиданной формы")

    with conn:
        for row, vector in zip(rows, vectors):
            conn.execute(
                """
                INSERT INTO ktru_position_embedding
                    (position_code, model_name, model_version, embedding)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(position_code) DO UPDATE SET
                    model_name = excluded.model_name,
                    model_version = excluded.model_version,
                    embedding = excluded.embedding,
                    created_at = CURRENT_TIMESTAMP
                """,
                (row["position_code"], model_name, model_version, vector.tobytes()),
            )
    return len(rows)


def encode_query(
    query: str,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
):
    """Encode one user query for semantic_search."""
    if np is None:
        raise RuntimeError("Для поиска по эмбеддингам требуется установить numpy")
    model = _load_embedding_model(model_name)
    vector = model.encode(
        [_embedding_text(query, "query")],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return np.asarray(vector[0], dtype=np.float32)


def search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
    query_embedding=None,
) -> list[dict]:
    lexical = bm25_search(conn, query)
    semantic = semantic_search(conn, query_embedding)
    rrf: dict[str, float] = {}
    for ranked in (lexical, semantic):
        for rank, code in enumerate(ranked, 1):
            rrf[code] = rrf.get(code, 0.0) + 1 / (60 + rank)
    if not rrf:
        return []
    candidates = ", ".join("?" for _ in rrf)
    clause, params = _active_clause()
    rows = conn.execute(
        f"""
        SELECT p.code AS ktru_code, p.name, p.status, p.okpd2_code,
               p.is_template, p.application_date_start, p.application_date_end
        FROM ktru_position p
        WHERE p.code IN ({candidates}) AND {clause}
        """,
        [*rrf.keys(), *params],
    ).fetchall()
    result = [
        {
            "ktru_code": row["ktru_code"],
            "name": row["name"],
            "status": row["status"],
            "okpd2_code": row["okpd2_code"],
            "rrf_score": rrf[row["ktru_code"]],
            "is_template": bool(row["is_template"])
        }
        for row in rows
    ]
    return sorted(result, key=lambda item: -item["rrf_score"])[:limit]
