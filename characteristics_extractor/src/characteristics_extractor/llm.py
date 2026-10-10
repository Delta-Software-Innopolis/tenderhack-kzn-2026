"""Bounded asynchronous JSON-schema requests to LM Studio; no automatic retries."""

import asyncio
import json

import httpx

from .config import LMStudioSettings


class LLMError(RuntimeError):
    code = "llm_error"


class LLMUnavailableError(LLMError):
    code = "llm_unavailable"


class LLMTimeoutError(LLMError):
    code = "llm_timeout"


class LLMTruncatedError(LLMError):
    code = "llm_output_truncated"


class LLMInvalidOutputError(LLMError):
    code = "llm_invalid_output"


class LLMLimitError(LLMError):
    code = "llm_size_limit"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Повторяющийся ключ JSON")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("Недопустимая константа JSON")


def parse_json(value: str | bytes):
    """Do not recover JSON fragments from prose, Markdown, or thinking blocks."""
    try:
        return json.loads(value, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise LLMInvalidOutputError("LM Studio вернул некорректный JSON") from error


class LMStudioClient:
    def __init__(self, settings: LMStudioSettings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self._transport = transport

    def build_payload(self, messages: list[dict[str, str]], schema: dict) -> dict:
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "ktru_extraction", "strict": True, "schema": schema},
            },
            "stream": False,
            "max_tokens": self.settings.max_tokens,
            "temperature": self.settings.temperature,
            "top_p": self.settings.top_p,
            "top_k": self.settings.top_k,
            "presence_penalty": self.settings.presence_penalty,
            "repeat_penalty": self.settings.repeat_penalty,
        }
        if self.settings.reasoning_effort is not None:
            payload["reasoning_effort"] = self.settings.reasoning_effort
        size = len(json.dumps(payload, ensure_ascii=False, allow_nan=False))
        if size > self.settings.max_prompt_chars:
            raise LLMLimitError("Запрос превышает лимит размера контекста; данные не были обрезаны")
        return payload

    async def complete(self, messages: list[dict[str, str]], schema: dict) -> dict:
        payload = self.build_payload(messages, schema)
        headers = {}
        if self.settings.api_key:
            headers["Authorization"] = "Bearer " + self.settings.api_key.get_secret_value()
        timeout = httpx.Timeout(self.settings.timeout_seconds, connect=self.settings.connect_timeout_seconds)
        try:
            # Total deadline includes all reads, even if a server trickles bytes.
            async with asyncio.timeout(self.settings.timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=timeout, headers=headers, transport=self._transport,
                    trust_env=False, follow_redirects=False,
                ) as client:
                    async with client.stream("POST", self.settings.base_url + "/chat/completions", json=payload) as response:
                        if response.status_code != 200:
                            raise LLMUnavailableError(f"LM Studio вернул HTTP {response.status_code}")
                        content = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(content) + len(chunk) > self.settings.max_response_bytes:
                                raise LLMLimitError("Ответ LM Studio превышает лимит размера")
                            content.extend(chunk)
        except (TimeoutError, httpx.TimeoutException) as error:
            raise LLMTimeoutError("Истёк лимит ожидания LM Studio") from error
        except httpx.RequestError as error:
            raise LLMUnavailableError("Не удалось подключиться к LM Studio") from error

        envelope = parse_json(bytes(content))
        if not isinstance(envelope, dict) or not isinstance(envelope.get("choices"), list) or len(envelope["choices"]) != 1:
            raise LLMInvalidOutputError("Ожидался один ответ модели в choices")
        choice = envelope["choices"][0]
        if not isinstance(choice, dict):
            raise LLMInvalidOutputError("Некорректный объект choices")
        if choice.get("finish_reason") == "length":
            raise LLMTruncatedError("Модель исчерпала max_tokens; незавершённый ответ отклонён")
        if choice.get("finish_reason") != "stop":
            raise LLMInvalidOutputError("Модель не завершила выдачу штатно")
        message = choice.get("message")
        if not isinstance(message, dict) or message.get("refusal") or message.get("tool_calls"):
            raise LLMInvalidOutputError("Ожидалось содержимое JSON без отказа или вызова инструментов")
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise LLMInvalidOutputError(
                "Модель вернула пустое содержимое. Если ответ попал в reasoning_content, "
                "отключите thinking: LM_STUDIO_REASONING_EFFORT=none (если модель поддерживает)."
            )
        result = parse_json(text)
        if not isinstance(result, dict):
            raise LLMInvalidOutputError("Результат извлечения должен быть JSON-объектом")
        return result
