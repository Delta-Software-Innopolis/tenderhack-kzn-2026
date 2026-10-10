"""HTTP service for KTRU candidate search."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from search import canonicalize_query, lemmatize, search

DB_PATH = Path(__file__).with_name("ktru.db")
DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173,"
    "http://127.0.0.1:5173,"
    "http://localhost:4173,"
    "http://127.0.0.1:4173"
)


def cors_origins() -> list[str]:
    value = os.getenv("SEARCH_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in value.split(",") if origin.strip()]


app = FastAPI(
    title="KTRU Search Service",
    version="0.1.0",
    description="Поиск кандидатов КТРУ по пользовательскому тексту.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=100)


class SearchResponse(BaseModel):
    query: str
    canonical_query: str
    lemmatized_query: str
    candidates: list[dict]


def connect_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail=f"База данных не найдена: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/health", tags=["Service"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/search",
    response_model=SearchResponse,
    tags=["Search"],
    summary="Найти кандидатов КТРУ",
)
def search_candidates(request: SearchRequest) -> SearchResponse:
    with closing(connect_db()) as conn:
        canonical_query = canonicalize_query(conn, request.query)
        candidates = search(conn, request.query, limit=request.limit)
        return SearchResponse(
            query=request.query,
            canonical_query=canonical_query,
            lemmatized_query=lemmatize(
                canonical_query,
                remove_stop_words=True,
            ),
            candidates=candidates,
        )
