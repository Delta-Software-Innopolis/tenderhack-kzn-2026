import asyncio
import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from characteristics_extractor.app import create_app
from characteristics_extractor.catalog import build_catalog, prepare_catalog
from characteristics_extractor.config import LMStudioSettings
from characteristics_extractor.llm import LMStudioClient
from characteristics_extractor.repository import CatalogUnavailableError, KtruRepository
from characteristics_extractor.schemas import ExtractRequest, SearchCandidate


SCHEMA = """
CREATE TABLE ktru_position (code TEXT PRIMARY KEY, name TEXT NOT NULL, okpd2_code TEXT);
CREATE TABLE ktru_characteristic (
    id INTEGER PRIMARY KEY, position_code TEXT, code TEXT, name TEXT, type INTEGER,
    kind INTEGER, is_required INTEGER, choice_type INTEGER
);
CREATE TABLE ktru_characteristic_value (
    id INTEGER PRIMARY KEY, characteristic_id INTEGER, value_code TEXT,
    quality_description TEXT, okei_code TEXT, okei_name TEXT, value_format TEXT,
    min_value REAL, max_value REAL, min_notation TEXT, max_notation TEXT, concrete_value REAL
);
"""


def candidate(code, name="Молоток"):
    return SearchCandidate(ktru_code=code, name=name, status="ACTIVE", okpd2_code="25.73.30.141",
                           rrf_score=0.029, is_template=False)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "каталог с пробелами.db"
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript(SCHEMA)
            db.executemany("INSERT INTO ktru_position VALUES (?, ?, ?)", [
                ("A", "Молоток", "25.73.30.141"),
                ("B", "Молоток", "25.73.30.141"),
                ("C", "Лопата", "25.99.29.120"),
                ("D", "Молоток", "25.73.30.141"),
                ("empty", "Товар без характеристик", None),
            ])
            db.executemany("INSERT INTO ktru_characteristic VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
                (1, "A", "length", "Длина рукоятки", 2, 1, 0, 1),
                (2, "A", "material", "Материал бойка", 1, 1, 1, 2),
                (3, "A", "handle_type", "Тип исполнения рукоятки", 2, 2, 0, 2),
                (11, "B", "length", "Длина рукоятки", 2, 1, 1, 2),
                (12, "B", "material", "Материал бойка", 1, 1, 0, 1),
                (21, "C", "length", "Длина рукоятки", 2, 1, 0, 1),
                (31, "D", "length", "Длина рукоятки", 2, 1, 0, 1),
            ])
            db.executemany("INSERT INTO ktru_characteristic_value VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                (101, 1, "length-a", None, "003", "Миллиметр", "N", 100, 150, "greaterOrEqual", "less", None),
                (102, 2, "steel-a", "Сталь", None, None, "S", None, None, None, None, None),
                (103, 3, "handle-1", None, None, None, "N", None, None, None, None, 1),
                (111, 11, "length-b", None, "003", "Миллиметр", "N", 150, 200, "greaterOrEqual", "less", None),
                (112, 12, "steel-b", "Сталь", None, None, "S", None, None, None, None, None),
                (121, 21, "length-c", None, "003", "Миллиметр", "N", 500, None, "greater", None, None),
                (131, 31, "length-d", None, "004", "Сантиметр", "N", 10, 20, "greaterOrEqual", "less", None),
            ])
        self.repository = KtruRepository(self.path)

    def test_repository_loads_only_requested_codes_in_first_occurrence_order(self):
        loaded = self.repository.load_positions(["B", "absent", "A", "B", "absent"])
        self.assertEqual([p.code for p in loaded.positions], ["B", "A"])
        self.assertEqual(loaded.missing_codes, ["absent"])
        self.assertEqual({c.position_code for p in loaded.positions for c in p.characteristics}, {"A", "B"})

    def test_repository_preserves_codes_ranges_text_and_numeric_categories(self):
        position = self.repository.load_positions(["A"]).positions[0]
        length, material, handle = position.characteristics
        self.assertEqual(length.values[0].okei_code, "003")
        self.assertEqual(length.values[0].min_notation, "greaterOrEqual")
        self.assertEqual(length.values[0].max_notation, "less")
        self.assertEqual(material.values[0].quality_description, "Сталь")
        self.assertEqual(handle.values[0].concrete_value, 1)
        self.assertIsNone(handle.values[0].okei_code)

    def test_reading_does_not_change_database_and_uses_readonly_uri(self):
        before = self.path.read_bytes()
        original_connect = sqlite3.connect
        with patch("characteristics_extractor.repository.sqlite3.connect", wraps=original_connect) as connect:
            self.repository.load_positions(["A"])
        self.assertTrue(connect.call_args.args[0].endswith("?mode=ro"))
        self.assertTrue(connect.call_args.kwargs["uri"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_database_is_not_created(self):
        missing = Path(self.temporary.name) / "not-created.db"
        with self.assertRaises(CatalogUnavailableError):
            KtruRepository(missing).load_positions(["A"])
        self.assertFalse(missing.exists())

    def test_incompatible_database_is_an_error_not_an_empty_catalog(self):
        wrong = Path(self.temporary.name) / "wrong.db"
        sqlite3.connect(wrong).close()
        with self.assertRaises(CatalogUnavailableError):
            KtruRepository(wrong).load_positions(["A"])

    def test_sql_parameters_do_not_interpret_candidate_code(self):
        code = "A') OR 1=1 --"
        loaded = self.repository.load_positions([code])
        self.assertEqual(loaded.positions, [])
        self.assertEqual(loaded.missing_codes, [code])

    def test_batching_does_not_lose_positions_or_values(self):
        self.repository.BATCH_SIZE = 1
        loaded = self.repository.load_positions(["B", "C", "A", "missing"])
        self.assertEqual([p.code for p in loaded.positions], ["B", "C", "A"])
        self.assertEqual(sum(len(c.values) for p in loaded.positions for c in p.characteristics), 6)
        self.assertEqual(loaded.missing_codes, ["missing"])

    def test_all_batches_share_one_database_snapshot(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
        self.repository.BATCH_SIZE = 1
        original_connect = sqlite3.connect
        committed = False

        def open_with_writer(*args, **kwargs):
            connection = original_connect(*args, **kwargs)

            def update_after_first_batch(statement):
                nonlocal committed
                if "SELECT code, name" in statement and "'B'" in statement and not committed:
                    with closing(original_connect(self.path)) as writer, writer:
                        writer.execute("UPDATE ktru_position SET name='Изменено' WHERE code='B'")
                    committed = True

            connection.set_trace_callback(update_after_first_batch)
            return connection

        with patch("characteristics_extractor.repository.sqlite3.connect", side_effect=open_with_writer):
            loaded = self.repository.load_positions(["A", "B"])
        self.assertTrue(committed)
        self.assertEqual(loaded.positions[1].name, "Молоток")
        self.assertEqual(self.repository.load_positions(["B"]).positions[0].name, "Изменено")

    def test_env_path_configuration(self):
        with patch.dict(os.environ, {"KTRU_DB_PATH": str(self.path)}):
            self.assertEqual(KtruRepository.from_env().db_path, self.path.resolve())

    def test_empty_candidates_and_missing_candidates_are_diagnostics(self):
        for inputs in ([], [candidate("absent")]):
            with self.subTest(inputs=inputs):
                context = prepare_catalog(inputs, self.repository)
                self.assertFalse(context.complete)
                self.assertTrue(context.issues)
                self.assertTrue(all(issue.blocking for issue in context.issues))
                self.assertEqual(context.candidates, inputs)

    def test_candidates_without_characteristics_are_nonblocking(self):
        for inputs in ([candidate("empty")], [candidate("empty"), candidate("A")]):
            with self.subTest(inputs=inputs):
                context = prepare_catalog(inputs, self.repository)
                self.assertTrue(context.complete)
                self.assertEqual(len(context.issues), 1)
                self.assertFalse(context.issues[0].blocking)
                self.assertEqual(context.issues[0].candidate_code, "empty")
                self.assertEqual(context.candidate_characteristic_ids["empty"], [])

    def test_http_empty_definitions_allow_extraction_and_stateless_continuation(self):
        async def check():
            for codes in (["empty"], ["empty", "A"]):
                for with_property in (False, True):
                    with self.subTest(codes=codes, with_property=with_property):
                        calls = []
                        query = "Кровать с надписью Альфа" if with_property else "Кровать"
                        facts = [{"source_text": "надписью Альфа", "occurrence": 0,
                                  "mention_type": "explicit", "extracted_name": "Надпись",
                                  "original_value": {"type": "string", "value": "Альфа", "unit": None},
                                  "characteristic_ids": []}] if with_property else []

                        def handle(request):
                            calls.append(request)
                            payload = json.loads(request.content)
                            if codes == ["empty"]:
                                ids = payload["response_format"]["json_schema"]["schema"]["$defs"]["ModelFact"]["properties"]["characteristic_ids"]
                                self.assertEqual(ids["maxItems"], 0)
                                self.assertNotIn("enum", ids["items"])
                            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
                                "content": json.dumps({"search_target": "Кровать", "facts": facts, "unsupported": []}),
                            }}]})

                        client = LMStudioClient(LMStudioSettings(model="test"), transport=httpx.MockTransport(handle))
                        body = {"query": query, "canonical_query": query, "lemmatized_query": query.lower(),
                                "candidates": [candidate(code).model_dump() for code in codes]}
                        app = create_app(repository=self.repository, client=client)
                        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
                            response = await http.post("/extract", json=body)
                        self.assertEqual(response.status_code, 200, response.text)
                        result = response.json()
                        self.assertEqual(result["status"], "completed")
                        self.assertEqual(result["search_target"], "Кровать")
                        self.assertEqual(result["clarifications"], [])
                        self.assertEqual(len(result["issues"]), 1)
                        self.assertFalse(result["issues"][0]["blocking"])
                        if with_property:
                            self.assertEqual(result["attributes"][0]["status"], "unknown")
                            self.assertEqual(result["attributes"][0]["message"], "Неизвестная характеристика")
                        else:
                            self.assertEqual(result["attributes"], [])
                        # Fresh server, no model configured, same warning exactly once.
                        app = create_app(repository=self.repository)
                        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
                            resumed = await http.post("/extract", json={**result, "candidates": body["candidates"]})
                        self.assertEqual(resumed.status_code, 200, resumed.text)
                        self.assertEqual(resumed.json(), result)
                        self.assertEqual(len(calls), 1)

        with patch("characteristics_extractor.app.load_environment"), patch.dict(os.environ, {}, clear=True):
            asyncio.run(check())

    def test_original_candidates_and_order_are_preserved_including_duplicates(self):
        inputs = [candidate("B"), candidate("C", "Лопата"), candidate("A"), candidate("B")]
        before = [item.model_dump() for item in inputs]
        context = prepare_catalog(inputs, self.repository)
        self.assertEqual([item.model_dump() for item in context.candidates], before)
        self.assertEqual([item.model_dump() for item in inputs], before)
        context.candidates[0].name = "Изменение копии"
        self.assertEqual(inputs[0].name, "Молоток")

    def test_equivalent_definitions_merge_without_merging_source_metadata(self):
        context = prepare_catalog([candidate("A"), candidate("B")], self.repository)
        self.assertTrue(context.complete)
        self.assertEqual(len(context.definitions), 3)
        length = next(d for d in context.definitions if d.code == "length")
        self.assertEqual([s.characteristic_row_id for s in length.sources], [1, 11])
        self.assertEqual([s.is_required for s in length.sources], [0, 1])
        self.assertEqual([s.choice_type for s in length.sources], [1, 2])
        self.assertEqual(len(length.values), 2)
        self.assertEqual({v.min_value for v in length.values}, {100, 150})
        self.assertIn(length.id, context.candidate_characteristic_ids["A"])
        self.assertIn(length.id, context.candidate_characteristic_ids["B"])
        self.assertEqual(context.get_definition(length.id), length)
        self.assertIsNone(context.get_definition("not-in-context"))

    def test_equal_values_keep_all_source_ids_and_value_codes(self):
        context = prepare_catalog([candidate("A"), candidate("B")], self.repository)
        material = next(d for d in context.definitions if d.code == "material")
        self.assertEqual(len(material.values), 1)
        value = material.values[0]
        self.assertEqual(value.quality_description, "Сталь")
        self.assertEqual([s.value_code for s in value.sources], ["steel-a", "steel-b"])
        self.assertEqual([s.value_row_id for s in value.sources], [102, 112])

    def test_same_label_different_product_or_units_remains_separate(self):
        context = prepare_catalog([candidate("A"), candidate("C", "Лопата"), candidate("D")], self.repository)
        lengths = [d for d in context.definitions if d.name == "Длина рукоятки"]
        self.assertEqual(len(lengths), 3)
        self.assertEqual({d.units[0].okei_code for d in lengths}, {"003", "004"})
        self.assertEqual({d.product_name for d in lengths}, {"Молоток", "Лопата"})

    def test_different_catalog_codes_or_types_do_not_merge(self):
        for field, replacement in (("code", "another_code"), ("type", 1), ("kind", 2)):
            with self.subTest(field=field):
                loaded = self.repository.load_positions(["A", "B"])
                setattr(loaded.positions[1].characteristics[0], field, replacement)
                context = build_catalog([candidate("A"), candidate("B")], loaded)
                self.assertEqual(len([d for d in context.definitions if d.name == "Длина рукоятки"]), 2)

    def test_no_catalog_code_uses_source_identity_instead_of_name_only(self):
        loaded = self.repository.load_positions(["A", "B"])
        for position in loaded.positions:
            position.characteristics[0].code = None
        context = build_catalog([candidate("A"), candidate("B")], loaded)
        self.assertEqual(len([d for d in context.definitions if d.name == "Длина рукоятки"]), 2)

    def test_ids_and_definitions_are_independent_of_order_and_subset(self):
        first = prepare_catalog([candidate("A"), candidate("B")], self.repository)
        reversed_context = prepare_catalog([candidate("B"), candidate("A")], self.repository)
        self.assertEqual(first.definitions, reversed_context.definitions)
        self.assertEqual(first.to_prompt_context(), reversed_context.to_prompt_context())
        subset = prepare_catalog([candidate("B")], self.repository)
        self.assertTrue({d.id for d in subset.definitions} <= {d.id for d in first.definitions})

    def test_catalog_rebuild_does_not_mutate_loaded_records(self):
        loaded = self.repository.load_positions(["A", "B"])
        before = loaded.model_dump()
        inputs = [candidate("A"), candidate("B")]
        self.assertEqual(build_catalog(inputs, loaded), build_catalog(inputs, loaded))
        self.assertEqual(loaded.model_dump(), before)

    def test_prompt_keeps_product_scope_and_numeric_codes_but_omits_ranges(self):
        context = prepare_catalog([candidate("A"), candidate("B"), candidate("C", "Лопата")], self.repository)
        prompt = context.to_prompt_context()
        self.assertEqual({p["product_name"] for p in prompt["products"]}, {"Молоток", "Лопата"})
        hammer = next(p for p in prompt["products"] if p["product_name"] == "Молоток")
        handle = next(c for c in hammer["characteristics"] if c["name"] == "Тип исполнения рукоятки")
        self.assertEqual(handle["numeric_values"], [1])
        self.assertEqual(handle["units"], [None])
        self.assertNotIn("min_value", json.dumps(prompt))
        self.assertNotIn("value_row_id", json.dumps(prompt))

    def test_missing_unit_metadata_is_retained_and_diagnosed(self):
        loaded = self.repository.load_positions(["A"])
        loaded.positions[0].characteristics[0].values[0].okei_name = None
        context = build_catalog([candidate("A")], loaded)
        self.assertFalse(context.complete)
        length = next(d for d in context.definitions if d.code == "length")
        self.assertEqual(length.units[0].okei_code, "003")
        self.assertIsNone(length.units[0].name)

    def test_empty_values_and_unknown_type_are_not_reported_as_unknown_characteristics(self):
        loaded = self.repository.load_positions(["A"])
        loaded.positions[0].characteristics[0].values = []
        loaded.positions[0].characteristics[1].type = 99
        context = build_catalog([candidate("A")], loaded)
        self.assertFalse(context.complete)
        self.assertEqual(len(context.definitions), 3)
        self.assertEqual({issue.code for issue in context.issues}, {"incomplete_catalog"})

    def test_fixture_contract_can_feed_repository_without_new_input_fields(self):
        path = Path(__file__).resolve().parents[1] / "examples" / "search_response.json"
        request = ExtractRequest.model_validate_json(path.read_text(encoding="utf-8"))
        # Fixture codes are deliberately absent in this test DB; every candidate remains.
        context = prepare_catalog(request.candidates, self.repository)
        self.assertEqual(context.candidates, request.candidates)
        self.assertEqual(len(context.issues), 10)
        self.assertEqual({issue.code for issue in context.issues}, {"candidate_not_found"})


if __name__ == "__main__":
    unittest.main()
