"""Smoke-test Ollama structured output with qwen3.5:4b.

Run from the repository root:
    uv run python test_llm.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = "qwen3.5:4b"

ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "characteristics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["key", "value"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["name", "characteristics"],
    "additionalProperties": False,
}


def ask_ollama(query: str) -> dict[str, Any]:
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Извлеки из пользовательского запроса название товара и его "
                    "явно указанные характеристики. Не придумывай отсутствующие "
                    "характеристики. Сохраняй единицы измерения в значениях. "
                    "Используй конкретные названия частей товара: например, для "
                    "молотка длина означает длину ручки, а покрытие — покрытие ручки."
                ),
            },
            {
                "role": "user",
                "content": "молоток 25см антискользящее покрытие",
            },
            {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "name": "Молоток",
                        "characteristics": [
                            {"key": "длина ручки", "value": "25см"},
                            {"key": "покрытие ручки", "value": "антискользящее"},
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
            {
                "role": "user",
                "content": query,
            }
        ],
        "format": ITEM_SCHEMA,
        "stream": False,
        "think": False,
        "options": {"temperature": 0},
    }
    request = Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        result = json.load(response)
    return json.loads(result["message"]["content"])


def validate_item(item: dict[str, Any]) -> None:
    if set(item) != {"name", "characteristics"}:
        raise ValueError(f"Unexpected fields: {sorted(item)}")
    if not isinstance(item["name"], str) or not item["name"].strip():
        raise TypeError("'name' must be a non-empty string")
    if not isinstance(item["characteristics"], list):
        raise TypeError("'characteristics' must be an array")
    for index, characteristic in enumerate(item["characteristics"]):
        if not isinstance(characteristic, dict) or set(characteristic) != {"key", "value"}:
            raise TypeError(f"characteristics[{index}] must contain only 'key' and 'value'")
        if not all(
            isinstance(characteristic[field], str) and characteristic[field].strip()
            for field in ("key", "value")
        ):
            raise TypeError(f"characteristics[{index}] values must be non-empty strings")


def main() -> int:
    print(f"Модель: {MODEL}")
    print("Введите описание товара. Пустая строка или Ctrl-D завершает программу.")
    while True:
        try:
            query = input("\nquery> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not query:
            break

        try:
            item = ask_ollama(query)
            validate_item(item)
        except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            print(f"Ollama request failed: {exc}", file=sys.stderr)
            continue
        except (TypeError, ValueError) as exc:
            print(f"Structured output validation failed: {exc}", file=sys.stderr)
            continue

        print(json.dumps(item, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
