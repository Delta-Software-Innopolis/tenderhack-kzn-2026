import asyncio
from contextlib import redirect_stdout
import io
import json
import unittest
from unittest.mock import patch

import httpx

from characteristics_extractor.app import create_app
from characteristics_extractor.config import LMStudioSettings
from characteristics_extractor.debug import debug_enabled
from characteristics_extractor.llm import LMStudioClient
from characteristics_extractor.repository import KtruRepository
from test_extraction import envelope, model_output, setup_context


class DebugPrintTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.request, self.catalog = setup_context()
        self.buffer = io.StringIO()
        for patcher in (
            patch("characteristics_extractor.app.load_environment"),
            patch("characteristics_extractor.pipeline.prepare_catalog", return_value=self.catalog),
            patch.dict("os.environ", {"EXTRACTOR_DEBUG_PRINT": "true", "LM_STUDIO_API_KEY": "test-secret-key"}, clear=True),
            redirect_stdout(self.buffer),
        ):
            patcher.__enter__()
            self.addCleanup(patcher.__exit__, None, None, None)

    def app(self, response=None):
        client = LMStudioClient(LMStudioSettings(model="test", api_key="test-secret-key"),
                                transport=httpx.MockTransport(lambda _: response if response is not None else httpx.Response(200, json=envelope())))
        return create_app(repository=KtruRepository("/unused.db"), client=client)

    def records(self):
        return [json.loads(line.removeprefix("[EXTRACTOR DEBUG] ")) for line in self.buffer.getvalue().splitlines()
                if line.startswith("[EXTRACTOR DEBUG] ")]

    async def post(self, app=None, **kwargs):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app or self.app(), raise_app_exceptions=False), base_url="http://test") as client:
            return await client.post("/extract", **(kwargs or {"json": self.request.model_dump()}))

    async def test_success_traces_actual_bodies_stages_and_timing(self):
        response = await self.post()
        self.assertEqual(response.status_code, 200)
        records = self.records()
        events = {record["event"]: record for record in records}
        self.assertEqual(events["http.request.body"]["body"], self.request.model_dump())
        self.assertEqual(events["http.response"]["body"], response.json())
        self.assertEqual(events["http.response"]["status"], 200)
        for event in ("pipeline.start", "catalog.loaded", "llm.request", "llm.response", "extraction.completed"):
            self.assertIn(event, events)
        self.assertEqual(len({r["request_id"] for r in records}), 1)
        self.assertTrue(all(r["elapsed_ms"] >= 0 for r in records))
        self.assertFalse(debug_enabled())
        self.assertNotIn("test-secret-key", self.buffer.getvalue())

    async def test_disabled_flag_preserves_response_and_prints_nothing(self):
        enabled = await self.post()
        self.buffer.truncate(0)
        self.buffer.seek(0)
        with patch.dict("os.environ", {"EXTRACTOR_DEBUG_PRINT": "false"}):
            disabled = await self.post()
        self.assertEqual(enabled.json(), disabled.json())
        self.assertEqual(self.buffer.getvalue(), "")

    async def test_validation_and_malformed_json_are_visible_before_endpoint(self):
        for arguments in ({"json": {"query": "Кровать"}},
                          {"content": '{"query":', "headers": {"Content-Type": "application/json"}}):
            response = await self.post(**arguments)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(self.records()[-1]["body"], response.json())
            self.assertEqual(self.records()[-1]["status"], 422)
        self.assertNotIn("pipeline.start", [r["event"] for r in self.records()])

    async def test_invalid_llm_shape_shows_raw_response_and_validation_cause(self):
        output = model_output()
        del output["search_target"]
        response = await self.post(app=self.app(httpx.Response(200, json=envelope(output))))
        self.assertEqual(response.status_code, 502)
        records = self.records()
        error = next(r for r in records if r["event"] == "error")
        self.assertEqual(error["exceptions"][0]["type"], "LLMInvalidOutputError")
        self.assertEqual(error["exceptions"][1]["type"], "ValidationError")
        self.assertEqual(error["exceptions"][1]["errors"][0]["loc"], ["search_target"])
        self.assertTrue(error["exceptions"][0]["traceback"])
        self.assertIn("llm.response", [r["event"] for r in records])
        self.assertEqual(records[-1]["body"], response.json())

    async def test_upstream_error_body_is_logged_and_credentials_are_redacted(self):
        response = await self.post(app=self.app(httpx.Response(400, json={
            "error": "model not loaded", "api_key": "another-secret", "detail": "test-secret-key",
        })))
        self.assertEqual(response.status_code, 503)
        record = next(r for r in self.records() if r["event"] == "llm.http_error")
        self.assertEqual(record["status"], 400)
        self.assertEqual(record["body"]["error"], "model not loaded")
        self.assertNotIn("another-secret", self.buffer.getvalue())
        self.assertNotIn("test-secret-key", self.buffer.getvalue())

    async def test_unhandled_exception_is_logged_and_stays_http_500(self):
        with patch("characteristics_extractor.pipeline.ExtractionService.process", side_effect=RuntimeError("unexpected failure")):
            response = await self.post()
        self.assertEqual(response.status_code, 500)
        records = self.records()
        self.assertEqual(records[-1]["event"], "http.unhandled_error")
        self.assertEqual(records[-2]["exceptions"][0]["message"], "unexpected failure")
        self.assertFalse(debug_enabled())

    async def test_concurrent_requests_have_separate_trace_ids(self):
        app = self.app()
        responses = await asyncio.gather(self.post(app), self.post(app))
        self.assertEqual([r.status_code for r in responses], [200, 200])
        starts = [r["request_id"] for r in self.records() if r["event"] == "http.request"]
        ends = [r["request_id"] for r in self.records() if r["event"] == "http.response"]
        self.assertEqual(len(set(starts)), 2)
        self.assertEqual(set(starts), set(ends))
