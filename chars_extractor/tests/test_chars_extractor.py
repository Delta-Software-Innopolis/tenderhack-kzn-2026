import hashlib
import importlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from chars_extractor import extract_characteristics


PROJECT = Path(__file__).resolve().parents[1]


class FakeModel:
    """Test the optional adapter and thresholds without downloading model weights."""

    def __init__(self, scores):
        self.scores = scores

    def encode_query(self, names, normalize_embeddings):
        return self

    def encode_document(self, names, normalize_embeddings):
        return self

    @property
    def T(self):
        return self

    def __matmul__(self, other):
        return [self]

    def tolist(self):
        return self.scores


class ExtractorTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db_path = Path(self.directory.name) / 'test.db'
        self.db = sqlite3.connect(self.db_path)
        self.addCleanup(self.db.close)
        self.db.executescript((PROJECT.parent / 'schema.sql').read_text())

    def item(self, code='A', name='Молоток'):
        self.db.execute('INSERT OR IGNORE INTO ktru_position (code, name) VALUES (?, ?)', (code, name))
        self.db.commit()

    def char(self, code, name, values):
        self.item(code)
        result = self.db.execute(
            'INSERT INTO ktru_characteristic (position_code, name) VALUES (?, ?)', (code, name),
        )
        characteristic_id = result.lastrowid
        for value in values:
            columns = ['characteristic_id', *value]
            self.db.execute(
                f'INSERT INTO ktru_characteristic_value ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})',
                [characteristic_id, *value.values()],
            )
        self.db.commit()
        return characteristic_id

    def length(self, code='A', low=100, high=150, closed_low=True, closed_high=False, unit='003', name='Длина рукоятки'):
        return self.char(code, name, [{
            'min_value': low, 'max_value': high,
            'min_notation': ('greaterOrEqual' if closed_low else 'greater') if low is not None else None,
            'max_notation': ('lessOrEqual' if closed_high else 'less') if high is not None else None,
            'okei_code': unit,
        }])

    def run_query(self, query, codes=None):
        result = extract_characteristics(query, codes or ['A'], db_path=self.db_path)
        json.dumps(result, allow_nan=False)
        return result

    def status(self, query, codes=None):
        result = self.run_query(query, codes)
        return (result['candidates'] + result['rejected_candidates'])[0]['matches'][0]['status']

    def test_point_at_exclusive_upper_boundary_matches_only_next_candidate(self):
        self.length('A', 100, 150)
        self.length('B', 150, 200)
        result = self.run_query('молоток длина ручка 15 сантиметр', ['A', 'B'])
        self.assertEqual([c['code'] for c in result['candidates']], ['B'])
        self.assertEqual([c['status'] for c in result['rejected_candidates']], ['mismatch'])
        self.assertEqual(result['chars'][0]['values'][0]['type'], 'number')
        self.assertEqual(result['chars'][0]['values'][0]['value'], 150)
        self.assertEqual(result['chars'][0]['values'][0]['unit'], 'мм')

    def test_inclusive_and_exclusive_lower_boundaries(self):
        self.length('A', 100, 150, False, True)
        self.assertEqual(self.status('длина ручка 10 см'), 'value_mismatch')
        self.assertEqual(self.status('длина ручка 15 см'), 'matched')

    def test_zero_and_exact_decimal_conversion(self):
        self.length('A', 0, 150, True, True)
        self.assertEqual(self.status('длина ручка 0 мм'), 'matched')
        self.assertEqual(self.status('длина ручка 0.15 метр'), 'matched')
        self.assertEqual(self.status('длина ручка 0,15 метр'), 'matched')
        self.assertEqual(self.status('длина ручка 0.15001 метр'), 'value_mismatch')

    def test_unitless_value_infers_single_unit(self):
        self.length()
        result = self.run_query('длина ручка 120')
        match = result['candidates'][0]['matches'][0]
        self.assertEqual(match['status'], 'matched')
        self.assertTrue(match['unit_inferred'])
        self.assertEqual(result['chars'][0]['values'][0]['unit'], 'мм')
        self.assertTrue(result['chars'][0]['unit_inferred'])

    def test_incompatible_units(self):
        self.length()
        self.assertEqual(self.status('длина ручка 120 кг'), 'unit_mismatch')

    def test_mass_alias_and_unit_conversion(self):
        self.char('A', 'Масса', [{'concrete_value': 1500, 'okei_code': '163'}])
        self.assertEqual(self.status('вес 1.5 кг'), 'matched')
        self.assertEqual(self.status('масса 2 кг'), 'value_mismatch')

    def test_unknown_units_are_not_silently_ignored(self):
        self.length()
        self.assertEqual(self.status('длина ручка 120 попугай'), 'unit_mismatch')

    def test_negative_temperature(self):
        self.char('A', 'Температура', [{'min_value': -20, 'max_value': 0,
                  'min_notation': 'greaterOrEqual', 'max_notation': 'lessOrEqual', 'okei_code': '280'}])
        self.assertEqual(self.status('температура -10 градус цельсия'), 'matched')

    def test_one_sided_query_and_catalog_intervals(self):
        self.length('A', 100, None)
        self.assertEqual(self.status('длина ручка не менее 15 см'), 'matched')
        self.assertEqual(self.status('длина ручка >= 150 мм'), 'matched')
        self.assertEqual(self.status('длина ручка меньше 10 см'), 'value_mismatch')
        self.assertEqual(self.status('длина ручка не более 15 см'), 'partial_match')

    def test_interval_partial_overlap_and_disjoint(self):
        self.length('A', 100, 200, True, True)
        self.assertEqual(self.status('длина ручка от 10 до 15 см'), 'matched')
        self.assertEqual(self.status('длина ручка 5-15 см'), 'partial_match')
        self.assertEqual(self.status('длина ручка 30–40 см'), 'value_mismatch')

    def test_interval_with_two_compatible_units(self):
        self.length('A', 100, 200, True, True)
        self.assertEqual(self.status('длина ручка от 10 см до 0.2 м'), 'matched')

    def test_union_covers_range_without_collapsing_gaps(self):
        values = [{'min_value': a, 'max_value': b, 'min_notation': 'greaterOrEqual',
                   'max_notation': 'lessOrEqual', 'okei_code': '003'} for a, b in [(100, 150), (150, 200)]]
        self.char('A', 'Длина рукоятки', values)
        self.assertEqual(self.status('длина ручка от 100 до 200 мм'), 'matched')
        self.db.execute('UPDATE ktru_characteristic_value SET min_value = 160 WHERE min_value = 150')
        self.db.commit()
        self.assertEqual(self.status('длина ручка от 100 до 200 мм'), 'partial_match')
        self.assertEqual(self.status('длина ручка 155 мм'), 'value_mismatch')

    def test_zero_width_gap_is_not_filled(self):
        self.char('A', 'Длина', [
            {'min_value': 0, 'max_value': 10, 'min_notation': 'greaterOrEqual', 'max_notation': 'less'},
            {'min_value': 10, 'max_value': 20, 'min_notation': 'greater', 'max_notation': 'lessOrEqual'},
        ])
        self.assertEqual(self.status('длина 10'), 'value_mismatch')
        self.assertEqual(self.status('длина от 0 до 20'), 'partial_match')

    def test_mixed_numeric_units_require_explicit_query_unit(self):
        self.char('A', 'Длина', [{'concrete_value': 100, 'okei_code': '003'},
                              {'concrete_value': 20, 'okei_code': '004'}])
        self.assertEqual(self.status('длина 100'), 'ambiguous')
        self.assertEqual(self.status('длина 10 см'), 'matched')

    def test_invalid_range_is_reported_not_guessed(self):
        self.length()
        result = self.run_query('длина ручка от 20 до 10 см')
        self.assertEqual(result['chars'], [])
        self.assertTrue(result['unrecognized'])
        self.assertEqual(result['rejected_candidates'][0]['status'], 'undetermined')

    def test_multiple_adjacent_and_comma_separated_characteristics(self):
        self.length()
        self.char('A', 'Материал рукоятки', [{'quality_description': 'Резина'}])
        for query in ['длина ручка 12 см материал ручка резина', 'длина ручка 12 см, материал ручка резина']:
            with self.subTest(query=query):
                result = self.run_query(query)
                self.assertEqual(len(result['chars']), 2)
                self.assertEqual(result['candidates'][0]['status'], 'matched')

    def test_implicit_material_and_explicit_length(self):
        self.length()
        self.char('A', 'Материал рукоятки', [{'quality_description': 'Древесина'}])
        result = self.run_query('молоток с деревянный ручка длина ручка 12 см')
        self.assertEqual(len(result['chars']), 2)
        self.assertEqual(result['candidates'][0]['status'], 'matched')

    def test_rubberized_is_coating_not_bulk_material(self):
        self.length()
        self.char('A', 'Материал рукоятки', [{'quality_description': 'Резина'}])
        result = self.run_query('молоток с прорезиненный ручка длина ручка 12 см')
        self.assertEqual(result['chars'][0]['name'], 'покрытие рукоятка')
        self.assertEqual([m['status'] for m in result['candidates'][0]['matches']], ['not_found', 'matched'])

    def test_named_and_implicit_shape(self):
        self.char('A', 'Форма бойка', [{'quality_description': 'Круглый'}])
        self.char('A', 'Форма носка', [{'quality_description': 'Клиновидный'}])
        self.assertEqual(self.status('форма боек круглый'), 'matched')
        self.assertEqual(self.status('круглый боек'), 'matched')

    def test_short_name_does_not_guess_between_two_parts(self):
        self.length(name='Длина рукоятки')
        self.length(name='Длина головки')
        self.assertEqual(self.status('длина 120 мм'), 'ambiguous')

    def test_implicit_value_accepts_any_field_but_explicit_component_is_preserved(self):
        self.char('A', 'Цвет корпуса', [{'quality_description': 'Красный'}])
        self.char('A', 'Цвет рукоятки', [{'quality_description': 'Красный'}])
        self.assertEqual(self.status('молоток красный'), 'matched')
        self.assertEqual(self.status('молоток красный ручка'), 'matched')
        self.assertEqual(self.status('цвет красный'), 'ambiguous')

    def test_mismatch_does_not_turn_into_not_found(self):
        self.char('A', 'Материал рукоятки', [{'quality_description': 'Резина'}])
        self.assertEqual(self.status('материал ручка дерево'), 'value_mismatch')

    def test_missing_attribute_is_retained(self):
        self.item()
        result = self.run_query('длина ручка 15 см')
        self.assertEqual(result['chars'][0]['values'][0]['value'], 15)
        self.assertEqual(result['rejected_candidates'][0]['matches'][0]['status'], 'not_found')

    def test_missing_catalog_values(self):
        self.char('A', 'Цвет', [])
        self.assertEqual(self.status('цвет красный'), 'not_comparable')

    def test_bad_catalog_boundary_is_not_silently_closed(self):
        self.char('A', 'Длина', [{'min_value': 1, 'max_value': 10, 'min_notation': 'unknown'}])
        self.assertEqual(self.status('длина 5'), 'not_comparable')

    def test_negation(self):
        self.char('A', 'Материал рукоятки', [{'quality_description': 'Резина'}])
        self.assertEqual(self.status('материал ручка не резина'), 'value_mismatch')
        self.assertEqual(self.status('материал ручка не дерево'), 'matched')

    def test_digit_string_value(self):
        self.char('A', 'Размер', [{'quality_description': '42'}])
        result = self.run_query('размер 42')
        self.assertEqual(result['chars'][0]['values'][0]['type'], 'string')
        self.assertEqual(result['candidates'][0]['status'], 'matched')

    def test_without_boolean_property(self):
        self.char('A', 'Наличие капюшона', [{'quality_description': 'Нет'}])
        self.assertEqual(self.status('без капюшон'), 'matched')
        self.assertEqual(self.status('с капюшон'), 'value_mismatch')

    def test_sources_refer_to_input(self):
        self.length()
        result = self.run_query('молоток, длина ручка 12 см')
        for char in result['chars']:
            self.assertEqual(result['query'][char['start']:char['end']], char['source'])

    def test_product_only_and_empty_queries_do_not_invent_requirements(self):
        self.length()
        for query in ('', 'молоток'):
            result = self.run_query(query)
            self.assertEqual(result['chars'], [])
            self.assertEqual(result['candidates'][0]['status'], 'no_constraints')

    def test_unrecognized_numeric_fragment_is_not_silently_dropped(self):
        self.length()
        result = self.run_query('молоток 15 см')
        self.assertTrue(result['unrecognized'])
        self.assertEqual(result['rejected_candidates'][0]['status'], 'undetermined')

    def test_candidate_order_deduplication_and_unknown_codes(self):
        self.length('A')
        self.length('B')
        result = self.run_query('длина 120 мм', ['B', 'missing', 'A', 'B', "' OR 1=1 --"])
        self.assertEqual([c['code'] for c in result['candidates']], ['B', 'A'])
        self.assertEqual(result['unknown_candidate_codes'], ['missing', "' OR 1=1 --"])

    def test_only_selected_candidates_are_considered(self):
        self.length('A')
        self.char('B', 'Материал', [{'quality_description': 'Адамантий'}])
        result = self.run_query('молоток адамантий', ['A'])
        self.assertEqual(result['chars'], [])
        self.assertTrue(result['unrecognized'])

    def test_no_candidates_does_not_open_database(self):
        result = extract_characteristics('длина 15 см', [], db_path='/missing/catalog.db')
        self.assertEqual(result['candidates'], [])
        self.assertEqual(result['chars'][0]['values'][0]['value'], 15)

    def test_missing_database_is_not_created(self):
        path = self.db_path.with_name('missing.db')
        with self.assertRaises(sqlite3.OperationalError):
            extract_characteristics('длина 15 см', ['A'], db_path=path)
        self.assertFalse(path.exists())

    def test_database_is_not_modified(self):
        self.length()
        self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        original = hashlib.sha256(self.db_path.read_bytes()).digest()
        self.run_query('длина ручка 12 см')
        self.assertEqual(hashlib.sha256(self.db_path.read_bytes()).digest(), original)

    def test_cli_and_lightweight_import(self):
        self.length()
        result = subprocess.run([sys.executable, str(PROJECT / 'chars_extractor.py'),
                                 'длина ручка 12 см', 'A', '--db', str(self.db_path)],
                                check=True, capture_output=True, text=True, cwd=self.directory.name)
        self.assertEqual(json.loads(result.stdout)['candidates'][0]['status'], 'matched')
        self.assertNotIn('sentence_transformers', sys.modules)
        self.assertNotIn('torch', sys.modules)

    def test_semantic_fallback_threshold_and_margin(self):
        self.char('A', 'Окраска корпуса', [{'quality_description': 'Красный'}])
        self.char('A', 'Расцветка рукоятки', [{'quality_description': 'Красный'}])
        module = importlib.import_module(extract_characteristics.__module__)
        for scores, expected in [([0.9, 0.5], 'matched'), ([0.9, 0.89], 'ambiguous'), ([0.4, 0.3], 'not_found')]:
            with self.subTest(scores=scores), patch.object(module, '_semantic_model', return_value=FakeModel(scores)):
                result = extract_characteristics('цвет красный', ['A'], db_path=self.db_path, semantic_model='fake')
                match = (result['candidates'] + result['rejected_candidates'])[0]['matches'][0]
                self.assertEqual(match['status'], expected)
                self.assertEqual(match['method'], 'semantic')

    def test_default_and_exact_name_modes_do_not_load_semantic_model(self):
        self.char('A', 'Окраска', [{'quality_description': 'Красный'}])
        module = importlib.import_module(extract_characteristics.__module__)
        with patch.object(module, '_semantic_model', side_effect=AssertionError('Unexpected model load')):
            result = self.run_query('цвет красный')
            self.assertEqual(result['rejected_candidates'][0]['matches'][0]['status'], 'not_found')
            self.length()
            result = extract_characteristics('длина ручка 120 мм', ['A'], db_path=self.db_path, semantic_model='fake')
            self.assertEqual(result['candidates'][0]['matches'][0]['status'], 'matched')

    def test_component_measurement_without_length_label(self):
        self.length('A', 100, 150)
        self.length('B', 150, 200)
        self.char('A', 'Материал рукоятки', [{'quality_description': 'Резина'}])
        result = self.run_query('молоток строительный ручка 10 см', ['B', 'A'])
        purpose, length = result['chars']
        self.assertEqual(purpose['mapping_status'], 'not_found')
        self.assertFalse(purpose['in_ktru'])
        self.assertEqual(purpose['values'][0]['value'], 'строительный')
        self.assertEqual(length['name'], 'Длина рукоятки')
        self.assertEqual(length['mapping_status'], 'mapped')
        self.assertEqual(length['values'], [{'name': 'Длина рукоятки', 'type': 'number',
                         'value': 100, 'unit': 'мм', 'value_code': None}])
        self.assertEqual(len(length['ktru_refs']), 2)
        self.assertIsNone(length['id'])
        self.assertEqual([c['code'] for c in result['candidates']], ['A'])
        self.assertEqual(result['candidates'][0]['status'], 'partial_match')
        self.assertEqual(result['rejected_candidates'][0]['code'], 'B')
        self.assertFalse(result['unrecognized'])
        # The catalogue structure is shared; the requested number isn't replaced by a bin.
        self.assertTrue(set(result['candidates'][0]['characteristics'][0]) <= set(length))

    def test_query_mass_has_catalogue_name_and_unit_and_keeps_exact_value(self):
        for code, low, high in [('A', 1.4, 1.6), ('B', 2, 2.5)]:
            self.char(code, 'Масса молотка', [{'min_value': low, 'max_value': high,
                'min_notation': 'greaterOrEqual', 'max_notation': 'less', 'okei_code': '166'}])
        for query in ['молоток строительный масса 1.5 кг', 'молоток строительный вес 1500 г']:
            with self.subTest(query=query):
                result = self.run_query(query, ['B', 'A'])
                mass = result['chars'][1]
                self.assertEqual(mass['name'], 'Масса молотка')
                self.assertEqual(mass['values'][0]['value'], 1.5)
                self.assertEqual(mass['values'][0]['unit'], 'кг')
                self.assertEqual(mass['values'][0]['type'], 'number')
                self.assertEqual([c['code'] for c in result['candidates']], ['A'])

    def test_query_range_is_converted_and_keeps_boundaries(self):
        self.length('A', 100, 300)
        result = self.run_query('ручка от 10 до 20 см')
        self.assertEqual(result['chars'][0]['values'][0]['value'],
                         {'min': 100, 'max': 200, 'min_inclusive': True, 'max_inclusive': True})
        self.assertEqual(result['chars'][0]['values'][0]['unit'], 'мм')
        result = self.run_query('длина ручка больше 10 см')
        self.assertEqual(result['chars'][0]['values'][0]['value'],
                         {'min': 100, 'max': None, 'min_inclusive': False, 'max_inclusive': False})

    def test_unknown_named_characteristics_remain_in_chars(self):
        self.length()
        for suffix, expected_value in [('водостойкость высокий', 'высокий'),
                                       ('ресурс 100 цикл', 100), ('маркировка: ABC', 'ABC')]:
            with self.subTest(suffix=suffix):
                result = self.run_query('молоток ручка 12 см, ' + suffix)
                unknown = result['chars'][1]
                self.assertFalse(unknown['in_ktru'])
                self.assertEqual(unknown['mapping_status'], 'not_found')
                self.assertEqual(unknown['values'][0]['value'], expected_value)
                self.assertIsNone(unknown['code'])
                self.assertEqual(unknown['ktru_refs'], [])
                self.assertEqual(result['candidates'][0]['status'], 'partial_match')
                self.assertFalse(result['unrecognized'])

    def test_no_positive_matches_means_no_similar_candidates(self):
        self.length()
        for query in ['материал ручка резина', 'длина ручка 1 кг', 'молоток загадочный']:
            with self.subTest(query=query):
                result = self.run_query(query)
                self.assertEqual(result['candidates'], [])
                self.assertEqual(len(result['rejected_candidates']), 1)

    def test_contradiction_excludes_even_when_other_characteristics_match(self):
        self.length('A')
        self.length('B')
        for code, value in [('A', 'Дерево'), ('B', 'Резина')]:
            self.char(code, 'Материал рукоятки', [{'quality_description': value}])
        result = self.run_query('ручка 12 см материал ручка резиновый', ['A', 'B'])
        self.assertEqual([c['code'] for c in result['candidates']], ['B'])
        self.assertEqual(result['chars'][1]['values'][0]['value'], 'Резина')
        self.assertEqual(result['rejected_candidates'][0]['status'], 'mismatch')

    def test_component_measurement_does_not_guess_between_dimensions(self):
        self.length(name='Длина рукоятки')
        self.length(name='Диаметр рукоятки')
        result = self.run_query('ручка 12 см')
        self.assertEqual(result['chars'][0]['mapping_status'], 'ambiguous')
        self.assertEqual(result['chars'][0]['values'][0]['value'], 12)
        self.assertEqual(result['candidates'], [])
        self.assertEqual(result['rejected_candidates'][0]['matches'][0]['status'], 'ambiguous')

    def test_unit_conflict_is_visible_in_query_characteristic(self):
        self.length()
        char = self.run_query('длина ручка 10 кг')['chars'][0]
        self.assertTrue(char['in_ktru'])
        self.assertEqual(char['mapping_status'], 'unit_mismatch')
        self.assertEqual(char['values'][0]['unit'], 'кг')

    def test_output_unit_does_not_depend_on_candidate_order(self):
        self.length('A', 100, 200, unit='003')
        self.length('B', 10, 20, unit='004')
        first = self.run_query('длина ручка 0.12 м', ['A', 'B'])
        second = self.run_query('длина ручка 0.12 м', ['B', 'A'])
        self.assertEqual(first['chars'][0]['values'], second['chars'][0]['values'])
        self.assertEqual(first['chars'][0]['values'][0]['value'], 120)
        self.assertEqual(len(first['candidates']), 2)

    def test_multiword_catalogue_values_are_not_treated_as_new_labels(self):
        self.char('A', 'Материал бойка', [{'quality_description': 'Сталь нержавеющая'}])
        result = self.run_query('молоток материал боек сталь нержавеющий')
        self.assertEqual(result['chars'][0]['values'][0]['value'], 'Сталь нержавеющая')
        self.assertEqual(len(result['chars']), 1)
        self.assertEqual(result['candidates'][0]['status'], 'matched')

    def test_true_duplicates_are_merged_with_all_row_references(self):
        ids = [self.char('A', 'Материал', [{'quality_description': 'Нейлон', 'value_code': code}])
               for code in ['v1', 'v2']]
        self.db.execute("UPDATE ktru_characteristic SET code='material' WHERE position_code='A'")
        self.db.commit()
        result = self.run_query('материал нейлон')
        self.assertEqual(result['candidates'][0]['status'], 'matched')
        characteristics = result['candidates'][0]['characteristics']
        self.assertEqual(len(characteristics), 1)
        self.assertEqual(characteristics[0]['source_ids'], ids)
        self.assertEqual(len(characteristics[0]['values']), 1)
        self.assertEqual(characteristics[0]['values'][0]['value_codes'], ['v1', 'v2'])
        self.assertEqual(result['chars'][0]['mapping_status'], 'mapped')
        self.assertEqual([ref['characteristic_id'] for ref in result['chars'][0]['ktru_refs']], ids)
        self.assertEqual(result['candidates'][0]['matches'][0]['characteristic_ids'], ids)

    def test_duplicate_numeric_rows_combine_intervals_without_bridging_gaps(self):
        self.length('A', 100, 150)
        self.length('A', 150, 200)
        result = self.run_query('длина ручка от 10 до 19 см')
        self.assertEqual(result['candidates'][0]['status'], 'matched')
        self.assertEqual(len(result['candidates'][0]['characteristics']), 1)
        self.assertEqual(len(result['candidates'][0]['characteristics'][0]['values']), 2)
        self.assertEqual(self.status('длина ручка 20 см'), 'value_mismatch')

    def test_same_code_on_different_candidates_does_not_share_values(self):
        for code, value in [('A', 'Нейлон'), ('B', 'Хлопок')]:
            self.char(code, 'Материал', [{'quality_description': value}])
        self.db.execute("UPDATE ktru_characteristic SET code='material'")
        self.db.commit()
        result = self.run_query('материал нейлон', ['B', 'A'])
        self.assertEqual([c['code'] for c in result['candidates']], ['A'])
        self.assertEqual(result['rejected_candidates'][0]['matches'][0]['status'], 'value_mismatch')

    def test_different_codes_with_same_name_are_not_merged(self):
        for code in ['first', 'second']:
            identifier = self.char('A', 'Материал', [{'quality_description': 'Нейлон'}])
            self.db.execute('UPDATE ktru_characteristic SET code=? WHERE id=?', (code, identifier))
        self.db.commit()
        result = self.run_query('материал нейлон')
        self.assertEqual(result['chars'][0]['mapping_status'], 'ambiguous')
        self.assertEqual(result['rejected_candidates'][0]['matches'][0]['status'], 'ambiguous')

    def test_any_material_does_not_require_both_roles_to_contain_nylon(self):
        main = 'Вид основного сырья в составе основного материала'
        additional = 'Вид дополнительного сырья в составе основного материала'
        for code, primary, secondary in [('A', 'Хлопок', 'Нейлон'), ('B', 'Нейлон', 'Хлопок'),
                                          ('C', 'Хлопок', 'Шерсть')]:
            self.char(code, main, [{'quality_description': primary}])
            self.char(code, additional, [{'quality_description': secondary}])
        result = self.run_query('молоток нейлон', ['A', 'B', 'C'])
        self.assertEqual([c['code'] for c in result['candidates']], ['A', 'B'])
        self.assertEqual(result['chars'][0]['mapping_status'], 'alternatives')
        self.assertEqual(result['chars'][0]['match_mode'], 'any')
        self.assertEqual(result['chars'][0]['values'][0]['value'], 'Нейлон')
        self.assertEqual(len(result['candidates'][0]['characteristics']), 2)
        for candidate in result['candidates']:
            match = candidate['matches'][0]
            self.assertEqual(match['status'], 'matched')
            self.assertEqual(len(match['matched_characteristic_ids']), 1)
        for query, expected in [('основное сырье нейлон', ['B']),
                                 ('основной сырье нейлон', ['B']),
                                 ('дополнительное сырье нейлон', ['A'])]:
            with self.subTest(query=query):
                result = self.run_query(query, ['A', 'B', 'C'])
                self.assertEqual([c['code'] for c in result['candidates']], expected)
                self.assertEqual(result['chars'][0]['mapping_status'], 'mapped')
                self.assertFalse(result['unrecognized'])

    def test_negation_does_not_use_existential_implicit_value_matching(self):
        self.char('A', 'Основное сырье', [{'quality_description': 'Нейлон'}])
        self.char('A', 'Дополнительное сырье', [{'quality_description': 'Нейлон'}])
        self.assertEqual(self.status('молоток не нейлон'), 'ambiguous')

    def test_only_one_catalogue_field_allows_implicit_material(self):
        self.char('A', 'Основное сырье', [{'quality_description': 'Хлопок'}])
        identifier = self.char('A', 'Дополнительное сырье', [{'quality_description': 'Нейлон'}])
        result = self.run_query('молоток нейлон')
        self.assertEqual(result['chars'][0]['name'], 'Дополнительное сырье')
        self.assertEqual(result['chars'][0]['mapping_status'], 'mapped')
        self.assertEqual(result['candidates'][0]['matches'][0]['characteristic_id'], identifier)


if __name__ == '__main__':
    unittest.main()
