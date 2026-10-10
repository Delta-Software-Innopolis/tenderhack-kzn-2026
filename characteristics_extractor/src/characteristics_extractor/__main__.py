"""Run the same stateless pipeline as HTTP, or inspect the initial LLM payload."""

import argparse
import asyncio
import json
from pathlib import Path
import sys

from pydantic import ValidationError

from .catalog import prepare_catalog
from .config import LMStudioSettings, load_environment
from .extraction import ExtractionInputError, extract_initial, prepare_extraction
from .llm import LLMError, LMStudioClient
from .pipeline import ExtractionService, RequestStateError
from .repository import CatalogUnavailableError, KtruRepository
from .schemas import ExtractRequest


def main() -> int:
    parser = argparse.ArgumentParser(description="Извлечение и нормализация характеристик через LM Studio")
    parser.add_argument("input", type=Path, help="JSON-ответ сервиса поиска")
    parser.add_argument("--dry-run", action="store_true", help="Показать payload без вызова модели")
    parser.add_argument("--initial-only", action="store_true", help="Показать промежуточные факты без нормализации")
    args = parser.parse_args()
    load_environment()
    try:
        request = ExtractRequest.model_validate_json(args.input.read_text(encoding="utf-8"))
        repository = KtruRepository.from_env()
        if args.dry_run or args.initial_only:
            context = prepare_catalog(request.candidates, repository)
            client = LMStudioClient(LMStudioSettings.from_env())
            if args.dry_run:
                messages, schema, _ = prepare_extraction(request, context)
                print(json.dumps(client.build_payload(messages, schema), ensure_ascii=False, indent=2))
            else:
                result = asyncio.run(extract_initial(request, context, client))
                print(result.model_dump_json(indent=2))
        else:
            result = asyncio.run(ExtractionService(repository).process(request))
            print(result.model_dump_json(indent=2))
        return 0
    except ValidationError as error:
        # Field paths are sufficient; don't echo environment values/API keys.
        fields = [".".join(map(str, item["loc"])) for item in error.errors()]
        print(json.dumps({"error": "validation_error", "fields": fields}, ensure_ascii=False), file=sys.stderr)
    except (LLMError, ExtractionInputError, RequestStateError, CatalogUnavailableError, OSError) as error:
        print(json.dumps({"error": getattr(error, "code", "input_error"), "message": str(error)}, ensure_ascii=False), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
