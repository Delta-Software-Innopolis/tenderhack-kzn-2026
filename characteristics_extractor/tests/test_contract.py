import copy
import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from characteristics_extractor import ExtractRequest, ExtractResponse


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "search_response.json"


def search_document(query="Молоток 500 г"):
    document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    document.update(query=query, canonical_query=query, lemmatized_query=query.lower(), search_target="Молоток")
    return document


def response_document(query="Молоток 500 г"):
    document = search_document(query)
    del document["candidates"]
    return document


def with_candidates(document):
    return {**document, "candidates": search_document()["candidates"]}


def pending_response():
    return {
        **response_document(),
        "status": "needs_clarification",
        "attributes": [{
            "id": "fact_1",
            "source_text": "500 г",
            "source_span": {"start": 8, "end": 13},
            "mention_type": "implicit",
            "status": "needs_clarification",
            "original_value": {"type": "number", "value": 500, "unit": "г"},
        }],
        "clarifications": [{
            "id": "question_1",
            "attribute_id": "fact_1",
            "kind": "choose_characteristic",
            "question": "Масса всего молотка или головки?",
            "options": [
                {"characteristic_id": "mass_total", "name": "Масса молотка"},
                {"characteristic_id": "mass_head", "name": "Масса головки молотка"},
            ],
        }],
    }


def completed_response():
    document = pending_response()
    document.update(status="completed", clarifications=[])
    document["attributes"][0].update(
        status="resolved",
        characteristic_id="mass_head",
        characteristic_name="Масса головки молотка",
        resolution_source="user",
        normalized_value={
            "type": "number", "value": 0.5,
            "unit": {"okei_code": "166", "name": "Килограмм"},
        },
    )
    return document


class ContractTests(unittest.TestCase):
    def test_accepts_exact_upstream_example_and_preserves_candidates(self):
        original = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        parsed = ExtractRequest.model_validate(original)
        self.assertTrue(parsed.is_initial)
        self.assertEqual(len(parsed.candidates), 10)
        self.assertEqual(parsed.model_dump(include=set(original)), original)

    def test_missing_and_null_attributes_mean_initial_but_empty_list_does_not(self):
        document = search_document()
        self.assertTrue(ExtractRequest.model_validate(with_candidates(document)).is_initial)
        document["attributes"] = None
        self.assertTrue(ExtractRequest.model_validate(with_candidates(document)).is_initial)
        document["attributes"] = []
        self.assertFalse(ExtractRequest.model_validate(with_candidates(document)).is_initial)

    def test_server_document_roundtrips_through_client_request(self):
        for document in (pending_response(), completed_response()):
            with self.subTest(status=document["status"]):
                response = ExtractResponse.model_validate(document)
                request = ExtractRequest.model_validate_json(json.dumps(with_candidates(response.model_dump())))
                self.assertEqual(request.model_dump(exclude={"candidates"}), response.model_dump())

    def test_client_can_select_id_without_filling_derived_fields(self):
        document = pending_response()
        document["clarifications"] = []
        document["attributes"][0].update(
            status="resolved", characteristic_id="mass_head", resolution_source="user",
        )
        request = ExtractRequest.model_validate(with_candidates(document))
        self.assertFalse(request.is_initial)
        self.assertIsNone(request.attributes[0].normalized_value)
        # The same client edit cannot be exposed as a finished server response.
        with self.assertRaises(ValidationError):
            ExtractResponse.model_validate(document)

    def test_clearing_questions_does_not_produce_valid_completed_response(self):
        document = pending_response()
        document.update(status="completed", clarifications=[])
        ExtractRequest.model_validate(with_candidates(document))
        with self.assertRaises(ValidationError):
            ExtractResponse.model_validate(document)

    def test_original_query_is_source_of_spans_not_lemmatized_query(self):
        document = pending_response()
        document["lemmatized_query"] = "молоток 500 грамм"
        ExtractResponse.model_validate(document)
        document["attributes"][0]["source_text"] = "500 грамм"
        with self.assertRaises(ValidationError):
            ExtractRequest.model_validate(with_candidates(document))

    def test_changed_query_cannot_reuse_old_source_references(self):
        document = completed_response()
        document["query"] = "Молоток 600 г"
        with self.assertRaises(ValidationError):
            ExtractRequest.model_validate(with_candidates(document))

    def test_unknown_is_a_completed_result_with_exact_message(self):
        document = response_document("Молоток гравировка дракон")
        document.update(status="completed", attributes=[{
            "id": "fact_1",
            "source_text": "гравировка дракон",
            "source_span": {"start": 8, "end": len(document["query"])},
            "mention_type": "explicit",
            "status": "unknown",
            "extracted_name": "Гравировка",
            "original_value": {"type": "string", "value": "дракон"},
            "message": "Неизвестная характеристика",
        }])
        ExtractResponse.model_validate(document)
        for change in (
            {"message": "Нет в КТРУ"},
            {"characteristic_id": "invented"},
            {"extracted_name": None},
        ):
            invalid = copy.deepcopy(document)
            invalid["attributes"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValidationError):
                ExtractResponse.model_validate(invalid)

    def test_no_characteristics_is_valid_completed_result(self):
        document = {**response_document("Молоток"), "attributes": [], "status": "completed"}
        response = ExtractResponse.model_validate(document)
        self.assertFalse(ExtractRequest.model_validate(with_candidates(response.model_dump())).is_initial)

    def test_unsupported_constraint_blocks_completion_without_equality_fact(self):
        document = {
            **response_document("Молоток не больше 500 г"),
            "attributes": [],
            "status": "needs_clarification",
            "issues": [{
                "id": "issue_1", "code": "unsupported_constraint", "blocking": True,
                "message": "Укажите конкретную массу вместо ограничения «не больше».",
            }],
        }
        ExtractResponse.model_validate(document)
        document["status"] = "completed"
        with self.assertRaises(ValidationError):
            ExtractResponse.model_validate(document)

    def test_references_and_question_options_are_checked(self):
        for change in ("missing_attribute", "duplicate_fact", "duplicate_option", "single_option"):
            document = pending_response()
            if change == "missing_attribute":
                document["clarifications"][0]["attribute_id"] = "missing"
            elif change == "duplicate_fact":
                document["attributes"].append(copy.deepcopy(document["attributes"][0]))
            elif change == "duplicate_option":
                options = document["clarifications"][0]["options"]
                options[1] = copy.deepcopy(options[0])
            else:
                document["clarifications"][0]["options"].pop()
            with self.subTest(change=change), self.assertRaises(ValidationError):
                ExtractRequest.model_validate(with_candidates(document))

    def test_resolved_attributes_cannot_have_pending_questions(self):
        document = completed_response()
        document["clarifications"] = pending_response()["clarifications"]
        with self.assertRaises(ValidationError):
            ExtractResponse.model_validate(document)

    def test_numbers_are_finite_and_not_booleans_or_strings(self):
        for value in (True, "500", float("nan"), float("inf")):
            document = pending_response()
            document["attributes"][0]["original_value"]["value"] = value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ExtractRequest.model_validate(with_candidates(document))

    def test_intervals_and_operators_are_not_allowed_in_attributes(self):
        document = pending_response()
        document["attributes"][0]["original_value"] = {
            "type": "interval", "min": 100, "max": 500, "unit": "г",
        }
        with self.assertRaises(ValidationError):
            ExtractRequest.model_validate(with_candidates(document))
        document = pending_response()
        document["attributes"][0]["operator"] = "lte"
        with self.assertRaises(ValidationError):
            ExtractRequest.model_validate(with_candidates(document))

    def test_okei_code_retains_leading_zeroes(self):
        document = completed_response()
        document.update(query="Молоток 15 см", canonical_query="Молоток 15 см",
                        lemmatized_query="молоток 15 см")
        document["attributes"][0].update(
            source_text="15 см", source_span={"start": 8, "end": 13},
            characteristic_id="handle_length", characteristic_name="Длина рукоятки",
            original_value={"type": "number", "value": 15, "unit": "см"},
            normalized_value={
                "type": "number", "value": 150,
                "unit": {"okei_code": "003", "name": "Миллиметр"},
            },
        )
        response = ExtractResponse.model_validate(document)
        self.assertIn('"okei_code":"003"', response.model_dump_json())

    def test_schema_generation_does_not_require_model_or_database(self):
        for model in (ExtractRequest, ExtractResponse):
            schema = model.model_json_schema()
            self.assertFalse(schema["additionalProperties"])
            if model is ExtractRequest:
                self.assertIn("candidates", schema["required"])
            else:
                self.assertNotIn("candidates", schema["properties"])
            json.dumps(schema)


if __name__ == "__main__":
    unittest.main()
