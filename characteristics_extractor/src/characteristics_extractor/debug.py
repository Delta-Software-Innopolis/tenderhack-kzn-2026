"""Opt-in request tracing; no request state is retained after completion."""

from contextvars import ContextVar
import json
import os
from time import perf_counter
import traceback
from uuid import uuid4

from pydantic import ValidationError


_trace: ContextVar[tuple[str, float] | None] = ContextVar("extractor_debug_trace", default=None)
_SECRET_FIELDS = {"authorization", "cookie", "set-cookie", "api_key", "token", "password", "lm_studio_api_key"}


def debug_enabled() -> bool:
    return _trace.get() is not None


def _redact(value):
    if isinstance(value, dict):
        return {key: "***" if str(key).lower() in _SECRET_FIELDS else _redact(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        secret = os.getenv("LM_STUDIO_API_KEY")
        return value.replace(secret, "***") if secret else value
    return value


def body_for_debug(body: bytes):
    try:
        return json.loads(body)
    except (ValueError, UnicodeError):
        return body.decode("utf-8", errors="replace")


def debug_print(event: str, **data) -> None:
    trace = _trace.get()
    if trace is None:
        return
    request_id, started = trace
    record = {"request_id": request_id, "event": event,
              "elapsed_ms": round((perf_counter() - started) * 1000, 1), **data}
    try:
        print("[EXTRACTOR DEBUG] " + json.dumps(_redact(record), ensure_ascii=False, default=str), flush=True)
    except OSError:
        # A closed output pipe must not change the API's behavior.
        pass


def debug_exception(error: Exception) -> None:
    if not debug_enabled():
        return
    chain = []
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        detail = {"type": type(error).__name__, "traceback": traceback.format_tb(error.__traceback__)}
        if isinstance(error, ValidationError):
            # Settings validation may contain credentials in its input values.
            detail["message"] = "Ошибка валидации: " + error.title
            detail["errors"] = error.errors(include_input=False, include_context=False)
        else:
            detail["message"] = str(error)
        chain.append(detail)
        error = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
    debug_print("error", exceptions=chain)


class DebugPrintMiddleware:
    def __init__(self, app, enabled: bool = False):
        self.app = app
        self.enabled = enabled

    async def __call__(self, scope, receive, send):
        if not self.enabled or scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = _trace.set((uuid4().hex, perf_counter()))
        request_body = bytearray()
        response_body = bytearray()
        status = None

        async def traced_receive():
            message = await receive()
            if message["type"] == "http.request":
                request_body.extend(message.get("body", b""))
                if not message.get("more_body", False):
                    debug_print("http.request.body", body=body_for_debug(bytes(request_body)))
            return message

        async def traced_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body":
                response_body.extend(message.get("body", b""))
                if not message.get("more_body", False):
                    debug_print("http.response", status=status, body=body_for_debug(bytes(response_body)))
            await send(message)

        try:
            debug_print("http.request", method=scope["method"], path=scope["path"])
            await self.app(scope, traced_receive, traced_send)
        except Exception as error:
            debug_exception(error)
            debug_print("http.unhandled_error", status=status or 500)
            raise
        finally:
            _trace.reset(token)
