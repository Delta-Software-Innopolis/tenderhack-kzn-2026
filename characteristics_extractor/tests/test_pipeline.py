import copy
import unittest
from unittest.mock import patch

import httpx

from characteristics_extractor.app import create_app
from characteristics_extractor.catalog import CatalogValue
from characteristics_extractor.config import LMStudioSettings
from characteristics_extractor.llm import LMStudioClient, LLMTimeoutError, LLMTruncatedError, LLMUnavailableError
from characteristics_extractor.normalization import NormalizationProblem, normalize_value
from characteristics_extractor.pipeline import ExtractionService, RequestStateError
from characteristics_extractor.repository import CatalogUnavailableError, KtruRepository
from characteristics_extractor.schemas import ExtractRequest, Issue, OriginalNumber, OriginalString
from characteristics_extractor.units import OKEI, UnitConversionError, convert

from test_extraction import setup_context, envelope, model_output


class UnitTests(unittest.TestCase):
    def test_conversions_include_decimal_area_offset_and_charge(self):
        for value, source, code, expected in (
            (15, "см", "003", 150), (0.1, "см", "003", 1),
            (500, "г", "166", 0.5), (2, "дюйма", "003", 50.8),
            (2, "см²", "050", 200), (1000, "мАч", "263", 1),
            (32, "°F", "280", 0), (2, "об/с", "331", 120),
            (5, "шт.", "796", 5), (2, "кВт", "212", 2000),
        ):
            with self.subTest(source=source, target=code):
                self.assertAlmostEqual(convert(value, source, code, "unit"), expected, places=10)

    def test_every_configured_unit_can_convert_to_itself(self):
        for code, spec in OKEI.items():
            with self.subTest(code=code):
                self.assertEqual(convert(3, spec.aliases[0], code, spec.aliases[0]), 3)

    def test_unknown_and_incompatible_units_are_not_guessed(self):
        for source, code, name in (("г", "003", "Миллиметр"), ("попугай", "003", "Миллиметр"),
                                   ("шт", "2355", "Градус"), ("см", "xyz", "Неизвестная")):
            with self.subTest(source=source, code=code), self.assertRaises(UnitConversionError):
                convert(15, source, code, name)
        self.assertEqual(convert(15, "Условная единица", "xyz", "условная единица"), 15)

    def test_numeric_value_is_not_snapped_to_catalog_range(self):
        _, context = setup_context()
        definition = context.definitions[0]
        definition.values = [CatalogValue(quality_description=None, concrete_value=None,
            min_value=100, max_value=200, min_notation="greaterOrEqual", max_notation="less",
            value_format="N", unit=definition.units[0])]
        result = normalize_value(OriginalNumber(type="number", value=999, unit="см"), definition)
        self.assertEqual(result.value, 9990)

    def test_qualitative_synonyms_use_official_spelling_and_unknown_values_ask(self):
        _, context = setup_context()
        definition = context.definitions[0].model_copy(update={"ktru_type": 1, "units": [None]})
        definition.values = [CatalogValue(quality_description="Сталь", concrete_value=None,
            min_value=None, max_value=None, min_notation=None, max_notation=None, value_format="S", unit=None)]
        self.assertEqual(normalize_value(OriginalString(type="string", value="стальной"), definition).value, "Сталь")
        with self.assertRaises(NormalizationProblem) as caught:
            normalize_value(OriginalString(type="string", value="деревянный"), definition)
        self.assertEqual(caught.exception.suggestions, ["Сталь"])


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.request, self.context = setup_context()
        self.calls = []
        self.response = envelope()
        def handler(request):
            self.calls.append(request)
            return httpx.Response(200, json=self.response)
        self.client = LMStudioClient(LMStudioSettings(model="test"), transport=httpx.MockTransport(handler))
        self.repository = KtruRepository("/unused.db")
        self.catalog_patch = patch("characteristics_extractor.pipeline.prepare_catalog", return_value=self.context)
        self.catalog_patch.start()
        self.addCleanup(self.catalog_patch.stop)
        # Unit tests must not depend on the developer's local .env or credentials.
        self.environment_patch = patch("characteristics_extractor.app.load_environment")
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)

    async def initial(self):
        return await ExtractionService(self.repository, self.client).process(self.request)

    async def resume(self, document):
        # New service, no model configured: all continuation state comes from JSON.
        with patch.dict("os.environ", {}, clear=True):
            return await ExtractionService(self.repository).process(ExtractRequest.model_validate({**document, "candidates": [c.model_dump() for c in self.request.candidates]}))

    async def test_initial_result_normalizes_omits_candidates_and_marks_unknown(self):
        result = await self.initial()
        self.assertNotIn("candidates", result.model_dump())
        self.assertEqual(result.search_target, "Молоток")
        self.assertEqual(result.attributes[0].normalized_value.value, 150)
        self.assertEqual(result.attributes[0].normalized_value.unit.okei_code, "003")
        self.assertEqual(result.attributes[2].message, "Неизвестная характеристика")
        self.assertEqual(len(result.attributes[1].characteristic_options), 2)
        self.assertEqual(len(result.clarifications), 1)
        self.assertEqual(result.status, "needs_clarification")

    async def test_clearing_questions_without_answer_regenerates_same_question(self):
        result = await self.initial()
        document = result.model_dump()
        document["clarifications"] = []
        resumed = await self.resume(document)
        self.assertEqual(resumed, result)
        self.assertEqual(len(self.calls), 1)

    async def test_user_choice_completes_on_new_service_and_derived_fields_are_recomputed(self):
        document = (await self.initial()).model_dump()
        attribute = document["attributes"][1]
        attribute.update(characteristic_id="mass_head", characteristic_name="Поддельное имя",
                         resolution_source="user", status="resolved",
                         normalized_value={"type": "number", "value": 999, "unit": None})
        document["clarifications"] = []
        resumed = await self.resume(document)
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(resumed.search_target, "Молоток")
        self.assertEqual(resumed.attributes[1].normalized_value.value, 0.5)
        self.assertEqual(resumed.attributes[1].characteristic_name, "Масса головки молотка")
        self.assertEqual(resumed.attributes[1].resolution_source, "user")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(await self.resume(resumed.model_dump()), resumed)

    async def test_choice_can_lead_to_unit_question_then_complete(self):
        document = (await self.initial()).model_dump()
        document["clarifications"] = []
        attribute = document["attributes"][1]
        attribute["characteristic_id"] = "mass_total"
        attribute["original_value"]["unit"] = "см"
        second = await self.resume(document)
        self.assertEqual(second.clarifications[0].kind, "specify_unit")
        document = second.model_dump()
        document["clarifications"] = []
        document["attributes"][1]["original_value"]["unit"] = "г"
        third = await self.resume(document)
        self.assertEqual(third.status, "completed")
        self.assertEqual(third.issues, [])
        self.assertEqual(len(self.calls), 1)

    async def test_outside_option_or_unknown_id_is_rejected(self):
        for identifier in ("length", "invented"):
            document = (await self.initial()).model_dump()
            document["clarifications"] = []
            document["attributes"][1]["characteristic_id"] = identifier
            with self.subTest(identifier=identifier), self.assertRaises(RequestStateError):
                await self.resume(document)

    async def test_changed_query_or_missing_fingerprint_requires_new_extraction(self):
        original = (await self.initial()).model_dump()
        for field, value in (("input_fingerprint", None), ("canonical_query", "изменено")):
            document = copy.deepcopy(original)
            document[field] = value
            with self.subTest(field=field), self.assertRaises(RequestStateError):
                await self.resume(document)

    async def test_lost_options_are_not_silently_converted_to_unknown(self):
        document = (await self.initial()).model_dump()
        document["clarifications"] = []
        document["attributes"][1]["characteristic_options"] = []
        with self.assertRaises(RequestStateError):
            await self.resume(document)

    async def test_empty_attributes_means_no_reextraction(self):
        self.response = envelope({"search_target": "Молоток", "facts": [], "unsupported": []})
        first = await self.initial()
        self.assertEqual(first.status, "completed")
        self.assertEqual(first.search_target, "Молоток")
        self.assertEqual(await self.resume(first.model_dump()), first)
        self.assertEqual(len(self.calls), 1)

    async def test_unknown_target_stays_null_on_continuation(self):
        output = model_output()
        output["search_target"] = None
        self.response = envelope(output)
        first = await self.initial()
        self.assertIn("search_target", first.model_dump())
        self.assertIsNone(first.search_target)
        document = first.model_dump()
        document["clarifications"] = []
        second = await self.resume(document)
        self.assertIsNone(second.search_target)
        self.assertEqual(len(self.calls), 1)

    async def test_initial_target_comes_from_extraction_not_client_or_first_candidate(self):
        self.request.search_target = "Устаревшая цель"
        output = model_output()
        output.update(search_target="Топор", facts=[])
        self.response = envelope(output)
        result = await self.initial()
        self.assertEqual(result.search_target, "Топор")
        self.assertNotIn("candidates", result.model_dump())

    async def test_unsupported_constraints_survive_cleared_questions(self):
        output = model_output()
        output["facts"] = []
        output["unsupported"] = [{"source_text": "500 г", "occurrence": 0, "reason": "inequality"}]
        self.response = envelope(output)
        first = await self.initial()
        self.assertEqual(first.status, "needs_clarification")
        second = await self.resume(first.model_dump())
        self.assertEqual(second.issues[0].code, "unsupported_constraint")

    async def test_http_cycle_across_two_app_instances_and_openapi(self):
        app = create_app(repository=self.repository, client=self.client)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            self.assertEqual((await http.get("/health")).status_code, 200)
            schema = (await http.get("/openapi.json")).json()
            self.assertIn("/extract", schema["paths"])
            self.assertNotIn("candidates", schema["components"]["schemas"]["ExtractResponse"]["properties"])
            first = await http.post("/extract", json=self.request.model_dump())
        self.assertEqual(first.status_code, 200, first.text)
        document = first.json()
        self.assertNotIn("candidates", document)
        document["candidates"] = [c.model_dump() for c in self.request.candidates]
        document["attributes"][1]["characteristic_id"] = "mass_head"
        document["clarifications"] = []
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(repository=self.repository)), base_url="http://test") as http:
            missing_candidates = {key: value for key, value in document.items() if key != "candidates"}
            missing = await http.post("/extract", json=missing_candidates)
            self.assertEqual(missing.status_code, 422)
            self.assertTrue(any(error["loc"] == ["body", "candidates"] for error in missing.json()["detail"]))
            second = await http.post("/extract", json=document)
            self.assertEqual(second.status_code, 200, second.text)
            self.assertEqual(second.json()["status"], "completed")
            self.assertNotIn("candidates", second.json())
            document["attributes"][1]["characteristic_id"] = "invented"
            self.assertEqual((await http.post("/extract", json=document)).status_code, 422)
        self.assertEqual(len(self.calls), 1)

    async def test_http_model_errors_have_explicit_statuses(self):
        for error, code in ((LLMTimeoutError("timeout"), 504), (LLMUnavailableError("offline"), 503),
                            (LLMTruncatedError("truncated"), 502)):
            with patch("characteristics_extractor.pipeline.extract_initial", side_effect=error):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(repository=self.repository, client=self.client)), base_url="http://test") as http:
                    result = await http.post("/extract", json=self.request.model_dump())
            with self.subTest(error=error):
                self.assertEqual(result.status_code, code)

    async def test_http_range_returns_clarification_preserves_scalar_and_resumes(self):
        query = "Молоток рукоятка 100-120 см, масса 500 г"
        self.request, _ = setup_context(query)
        facts = []
        for value in (100, 120):
            fact = model_output()["facts"][0]
            fact.update(source_text="рукоятка 100-120 см",
                        original_value={"type": "number", "value": value, "unit": "см"})
            facts.append(fact)
        mass = model_output()["facts"][1]
        mass["characteristic_ids"] = ["c2"]
        mass["occurrence"] = 1  # Real 4B response uses the fact index here.
        self.response = envelope({"search_target": "Молоток", "facts": facts + [mass], "unsupported": []})
        app = create_app(repository=self.repository, client=self.client)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            response = await http.post("/extract", json=self.request.model_dump())
        self.assertEqual(response.status_code, 200, response.text)
        document = response.json()
        self.assertEqual(document["status"], "needs_clarification")
        self.assertEqual(len(document["attributes"]), 1)
        self.assertEqual(document["attributes"][0]["normalized_value"]["value"], 0.5)
        self.assertEqual(document["issues"][0]["source_text"], "100-120 см")
        self.assertEqual(document["issues"][0]["code"], "unsupported_constraint")
        self.assertNotIn("candidates", document)
        document["clarifications"] = []
        resumed = await self.resume(document)
        self.assertEqual(resumed.status, "needs_clarification")
        self.assertEqual(len(resumed.issues), 1)
        self.assertEqual(len(self.calls), 1)

    async def test_http_catalog_failures_do_not_call_model(self):
        incomplete = self.context.model_copy(update={"issues": [Issue(
            id="missing", code="candidate_not_found", message="Не найден", blocking=True, candidate_code="A") ]})
        for value, error, code in ((incomplete, None, 409), (None, CatalogUnavailableError("Ошибка чтения"), 503)):
            with patch("characteristics_extractor.pipeline.prepare_catalog", return_value=value, side_effect=error):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(repository=self.repository, client=self.client)), base_url="http://test") as http:
                    result = await http.post("/extract", json=self.request.model_dump())
            self.assertEqual(result.status_code, code)
        self.assertEqual(self.calls, [])

    async def test_http_missing_model_configuration_is_503(self):
        with patch.dict("os.environ", {}, clear=True):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(repository=self.repository)), base_url="http://test") as http:
                result = await http.post("/extract", json=self.request.model_dump())
        self.assertEqual(result.status_code, 503, result.text)
        self.assertEqual(result.json()["detail"]["code"], "configuration_error")


if __name__ == "__main__":
    unittest.main()
