"""FastAPI app factory. No model or database is loaded on module import."""

import os
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .api_docs import EXTRACT_DESCRIPTION, EXTRACT_RESPONSES, REQUEST_EXAMPLES, HealthResponse
from .config import load_environment
from .extraction import IncompleteCatalogError
from .llm import LLMError, LLMTimeoutError, LLMUnavailableError, LMStudioClient
from .pipeline import ExtractionService, RequestStateError
from .repository import CatalogUnavailableError, KtruRepository
from .schemas import ExtractRequest, ExtractResponse


def create_app(*, repository: KtruRepository | None = None, client: LMStudioClient | None = None) -> FastAPI:
    load_environment()
    service = ExtractionService(repository or KtruRepository.from_env(), client)
    app = FastAPI(title="Characteristics Extractor", version="0.1.0", description=(
        "Stateless-извлечение характеристик КТРУ. Принимает ответ поиска целиком. "
        "При уточнении принимает собственный ответ с изменёнными attributes и добавленным исходным candidates. "
        "Кандидаты не фильтруются и не возвращаются в ответе."
    ), docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json",
        openapi_tags=[
            {"name": "Характеристики", "description": "Извлечение, нормализация и stateless-уточнения."},
            {"name": "Состояние", "description": "Доступность HTTP-процесса."},
        ])
    origins = os.getenv("EXTRACTOR_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in origins if origin.strip()],
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"], allow_credentials=False)

    @app.get("/health", response_model=HealthResponse, operation_id="getHealth", tags=["Состояние"],
             summary="Проверить доступность сервиса",
             description="Проверяет только HTTP-процесс. Не обращается к LM Studio и базе КТРУ.")
    def health():
        return {"status": "ok"}

    @app.post("/extract", response_model=ExtractResponse, operation_id="extractCharacteristics",
              tags=["Характеристики"], summary="Извлечь характеристики или обработать уточнение",
              description=EXTRACT_DESCRIPTION, responses=EXTRACT_RESPONSES)
    async def extract(request: Annotated[ExtractRequest, Body(openapi_examples=REQUEST_EXAMPLES)]):
        try:
            return await service.process(request)
        except RequestStateError as error:
            raise HTTPException(422, detail={"code": "invalid_state", "message": str(error)}) from error
        except IncompleteCatalogError as error:
            raise HTTPException(409, detail={"code": "incomplete_catalog", "message": str(error),
                                            "issues": [issue.model_dump() for issue in error.issues]}) from error
        except CatalogUnavailableError as error:
            raise HTTPException(503, detail={"code": "catalog_unavailable", "message": str(error)}) from error
        except LLMError as error:
            status = 504 if isinstance(error, LLMTimeoutError) else 503 if isinstance(error, LLMUnavailableError) else 502
            raise HTTPException(status, detail={"code": error.code, "message": str(error)}) from error
        except ValidationError as error:
            # Only settings validation is expected here; response invariant bugs
            # must not be misreported as user input errors or expose source data.
            if error.title != "LMStudioSettings":
                raise
            raise HTTPException(503, detail={"code": "configuration_error", "message": "Проверьте переменные LM_STUDIO_*"}) from error

    return app
