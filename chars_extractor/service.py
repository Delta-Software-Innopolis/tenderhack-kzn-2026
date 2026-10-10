"""Standalone HTTP service: uv run uvicorn service:app --port 8001 --reload."""

import logging
import os
from pathlib import Path
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

if __package__:
    from .api_models import ExtractRequest, ExtractResponse, HealthResponse, SearchResponseRequest, ServiceError
    from .chars_extractor import DEFAULT_DB_PATH, extract_characteristics
else:
    from api_models import ExtractRequest, ExtractResponse, HealthResponse, SearchResponseRequest, ServiceError
    from chars_extractor import DEFAULT_DB_PATH, extract_characteristics


CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]
LOGGER = logging.getLogger(__name__)
UNAVAILABLE_RESPONSE = {
    503: {
        "model": ServiceError,
        "description": "База КТРУ или настроенная семантическая модель недоступна",
        "content": {"application/json": {"example": {"detail": "Каталог КТРУ недоступен"}}},
    },
}


def create_app(*, db_path: str | Path | None = None, semantic_model: str | None = None) -> FastAPI:
    """Read configuration once per process; no database or model is loaded on import."""
    database = Path(db_path if db_path is not None else os.environ.get("CHARS_EXTRACTOR_DB_PATH", DEFAULT_DB_PATH)).resolve()
    model = semantic_model if semantic_model is not None else os.environ.get("CHARS_EXTRACTOR_SEMANTIC_MODEL") or None
    app = FastAPI(
        title="Сервис извлечения характеристик КТРУ",
        version="0.2.0",
        description=(
            "Извлекает требования из нормализованного запроса и сопоставляет их только с переданными "
            "кандидатами КТРУ. Поддерживает строки, числа, интервалы и перевод единиц измерения. "
            "chars содержит требования в структуре характеристик КТРУ и единицах каталога. "
            "candidates содержит подходящие и частично подходящие товары, rejected_candidates — исключённые. "
            "Новые кандидаты не ищутся, база открывается только для чтения. "
            "Неправильная структура запроса возвращает HTTP 422."
        ),
        openapi_tags=[
            {"name": "Характеристики", "description": "Извлечение и сопоставление требований"},
            {"name": "Сервис", "description": "Состояние HTTP-сервиса"},
        ],
    )
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                       allow_methods=["GET", "POST"], allow_headers=["*"])

    def run_extraction(query: str, codes: list[str]):
        try:
            return extract_characteristics(query, codes, db_path=database, semantic_model=model)
        except sqlite3.Error as error:
            LOGGER.exception("Не удалось прочитать каталог КТРУ")
            raise HTTPException(status_code=503, detail="Каталог КТРУ недоступен") from error
        except (RuntimeError, OSError) as error:
            LOGGER.exception("Недоступны ресурсы экстрактора")
            raise HTTPException(status_code=503, detail="Ресурсы экстрактора недоступны; проверьте конфигурацию сервера") from error

    @app.get("/health", response_model=HealthResponse, tags=["Сервис"],
             summary="Проверить работу HTTP-сервиса", operation_id="getExtractorHealth")
    def health():
        return {"status": "ok"}

    @app.post("/extract", response_model=ExtractResponse, response_model_exclude_unset=True,
              tags=["Характеристики"], summary="Извлечь характеристики для списка кодов КТРУ",
              operation_id="extractCharacteristics", responses=UNAVAILABLE_RESPONSE)
    def extract_endpoint(request: ExtractRequest):
        """Принимает normalized_query и candidate_codes.

        Неизвестные коды возвращаются в unknown_candidate_codes с HTTP 200.
        Пустой список кандидатов допустим. Интервал проверяется с учётом открытых
        границ; число из запроса переводится в единицы КТРУ и в ответе.
        Неизвестные характеристики сохраняются с mapping_status=not_found.
        Неявное значение в нескольких полях КТРУ возвращается с
        mapping_status=alternatives, match_mode=any: достаточно одного совпадения.
        Частичное совпадение помечается partial_match; любое явное противоречие
        исключает кандидата. Без подтверждённых совпадений кандидат также исключается,
        кроме запроса без характеристик. Причины доступны в rejected_candidates.
        """
        return run_extraction(request.normalized_query, request.candidate_codes)

    @app.post("/extract/from-search", response_model=ExtractResponse, response_model_exclude_unset=True,
              tags=["Характеристики"], summary="Обработать готовый ответ сервиса поиска",
              operation_id="extractCharacteristicsFromSearch", responses=UNAVAILABLE_RESPONSE)
    def extract_search_endpoint(request: SearchResponseRequest):
        """Использует lemmatized_query и candidates[].ktru_code из готового JSON.

        HTTP-запрос к поиску не выполняется. Метаданные поиска (query, canonical_query,
        name, status, okpd2_code, rrf_score) не влияют на сопоставление и не копируются
        в ответ. Порядок отобранных кандидатов сохраняется, повторные коды удаляются.
        """
        return run_extraction(request.lemmatized_query, [c.ktru_code for c in request.candidates])

    return app


app = create_app()
