import hashlib
import importlib
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from chars_extractor import extract_characteristics

# Support both `cd chars_extractor; uv run ...` and tests launched from the repo.
try:
    from chars_extractor.service import CORS_ORIGINS, create_app
except ModuleNotFoundError:
    from service import CORS_ORIGINS, create_app


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'catalog.db'
        with sqlite3.connect(self.path) as db:
            db.executescript((Path(__file__).resolve().parents[2] / 'schema.sql').read_text())
            for code in ('A', 'B'):
                db.execute('INSERT INTO ktru_position (code, name) VALUES (?, ?)', (code, 'Молоток'))
                char_id = db.execute('INSERT INTO ktru_characteristic (position_code, name) VALUES (?, ?)',
                                     (code, 'Длина рукоятки')).lastrowid
                low, high = (100, 150) if code == 'A' else (150, 200)
                db.execute('''INSERT INTO ktru_characteristic_value
                    (characteristic_id, min_value, max_value, min_notation, max_notation, okei_code)
                    VALUES (?, ?, ?, 'greaterOrEqual', 'less', '003')''', (char_id, low, high))
        db.close()
        self.client = self.enterContext(TestClient(create_app(db_path=self.path)))
        self.payload = {'normalized_query': 'молоток длина ручка 15 см', 'candidate_codes': ['A', 'B']}

    def test_http_response_preserves_extractor_result_and_unit_conversion(self):
        response = self.client.post('/extract', json=self.payload)
        self.assertEqual(response.status_code, 200)
        expected = extract_characteristics(**self.payload, db_path=self.path)
        self.assertEqual(response.json(), expected)
        self.assertEqual([c['status'] for c in response.json()['candidates']], ['matched'])
        self.assertEqual(response.json()['candidates'][0]['characteristics'][0]['values'][0]['type'], 'interval')
        self.assertEqual(response.json()['rejected_candidates'][0]['code'], 'A')
        self.assertEqual(response.json()['chars'][0]['values'][0]['value'], 150)

    def test_complete_search_payload_and_original_ranking(self):
        payload = {
            'query': 'Другая исходная формулировка', 'canonical_query': 'Не используется',
            'lemmatized_query': self.payload['normalized_query'],
            'candidates': [{'ktru_code': code, 'name': 'Поисковое имя', 'status': 'ACTIVE',
                            'okpd2_code': '25.73', 'rrf_score': score}
                           for code, score in [('B', 0.8), ('A', 0.7)]],
        }
        response = self.client.post('/extract/from-search', json=payload)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result['query'], self.payload['normalized_query'])
        self.assertEqual([c['code'] for c in result['candidates']], ['B'])
        self.assertEqual([c['status'] for c in result['candidates']], ['matched'])
        self.assertNotIn('rrf_score', result['candidates'][0])

    def test_input_validation(self):
        for body in ({}, {'normalized_query': 'x'}, {'candidate_codes': []},
                     {'normalized_query': 12, 'candidate_codes': []},
                     {'normalized_query': 'x', 'candidate_codes': [' ']},
                     {'normalized_query': 'x', 'candidate_codes': [42]},
                     {**self.payload, 'db_path': '/other/catalog.db'}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post('/extract', json=body).status_code, 422)
        for body in ({'query': 'x', 'candidates': []},
                     {'lemmatized_query': 'x', 'candidates': [{'code': 'A'}]}):
            self.assertEqual(self.client.post('/extract/from-search', json=body).status_code, 422)
        self.assertEqual(self.client.post('/extract', content='{', headers={'Content-Type': 'application/json'}).status_code, 422)

    def test_empty_unknown_and_duplicate_candidates(self):
        response = self.client.post('/extract', json={'normalized_query': '', 'candidate_codes': []})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['candidates'], [])
        response = self.client.post('/extract', json={**self.payload, 'candidate_codes': ['B', 'unknown', 'B']})
        self.assertEqual([c['code'] for c in response.json()['candidates']], ['B'])
        self.assertEqual(response.json()['unknown_candidate_codes'], ['unknown'])

    def test_health_and_documentation(self):
        self.assertEqual(self.client.get('/health').json(), {'status': 'ok'})
        for endpoint in ('/docs', '/redoc'):
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 200)
            self.assertIn('/openapi.json', response.text)
        schema = self.client.get('/openapi.json').json()
        for path in ('/extract', '/extract/from-search'):
            self.assertEqual(set(schema['paths'][path]['post']['responses']), {'200', '422', '503'})
        model = schema['components']['schemas']['QueryCharacteristic']
        self.assertEqual(model['properties']['values']['items']['discriminator']['propertyName'], 'type')
        self.assertEqual(set(model['properties']['values']['items']['discriminator']['mapping']), {'number', 'string', 'interval'})

    def test_missing_database_returns_503_without_creating_file(self):
        path = self.path.with_name('missing.db')
        with TestClient(create_app(db_path=path)) as client, self.assertLogs(level='ERROR'):
            response = client.post('/extract', json=self.payload)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'detail': 'Каталог КТРУ недоступен'})
        self.assertFalse(path.exists())

    def test_model_resource_error_is_documented_503(self):
        module = importlib.import_module(create_app.__module__)
        with patch.object(module, 'extract_characteristics', side_effect=RuntimeError('model unavailable')):
            with self.assertLogs(level='ERROR'):
                self.assertEqual(self.client.post('/extract', json=self.payload).status_code, 503)

    def test_cors_preflight_and_errors(self):
        origin = CORS_ORIGINS[0]
        response = self.client.options('/extract', headers={'Origin': origin,
            'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'Content-Type'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['access-control-allow-origin'], origin)
        response = self.client.post('/extract', json={}, headers={'Origin': origin})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.headers['access-control-allow-origin'], origin)

    def test_read_only_and_no_heavy_imports(self):
        before = hashlib.sha256(self.path.read_bytes()).digest()
        self.client.post('/extract', json=self.payload)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).digest(), before)
        self.assertNotIn('torch', sys.modules)
        self.assertNotIn('sentence_transformers', sys.modules)

    def test_from_search_returns_requested_chars_and_filtered_candidates(self):
        response = self.client.post('/extract/from-search', json={
            'query': 'молоток строительный ручка 10 см',
            'canonical_query': 'молоток строительный ручка 10 см',
            'lemmatized_query': 'молоток строительный ручка 10 см',
            'candidates': [{'ktru_code': code, 'is_template': False} for code in ['B', 'A']],
        })
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual([c['code'] for c in result['candidates']], ['A'])
        self.assertEqual([c['code'] for c in result['rejected_candidates']], ['B'])
        self.assertEqual(result['chars'][0]['mapping_status'], 'not_found')
        self.assertEqual(result['chars'][1]['values'][0]['value'], 100)
        self.assertEqual(result['chars'][1]['values'][0]['unit'], 'мм')
        self.assertEqual(result['chars'][1]['name'], 'Длина рукоятки')

    def test_reported_queries_against_real_catalogue(self):
        path = Path(__file__).resolve().parents[2] / 'ktru.db'
        if not path.exists():
            self.skipTest('Реальный каталог отсутствует; сценарии проверяются на тестовой базе')
        before = hashlib.sha256(path.read_bytes()).digest()
        codes = [f'25.73.30.141-000000{i:02}' for i in [5, 6, 10, 1, 4, 2, 3, 7, 8, 9]]
        with TestClient(create_app(db_path=path)) as client:
            for query, name, amount, unit, selected in [
                ('молоток строительный ручка 10 см', 'Длина рукоятки', 100, 'мм', codes),
                ('молоток строительный масса 1.5 кг', 'Масса молотка', 1.5, 'кг', codes),
                ('молоток строительный масса 1500 г', 'Масса молотка', 1.5, 'кг', codes),
                ('молоток плотничный ручка 10 см', 'Длина рукоятки', 100, 'мм', [codes[-1]]),
            ]:
                with self.subTest(query=query):
                    response = client.post('/extract/from-search', json={
                        'query': query, 'canonical_query': query, 'lemmatized_query': query,
                        'candidates': [{'ktru_code': code, 'name': 'Молоток', 'status': 'ACTIVE',
                                        'okpd2_code': '25.73.30.141', 'rrf_score': 0.01,
                                        'is_template': False} for code in codes]})
                    self.assertEqual(response.status_code, 200)
                    result = response.json()
                    char = next(c for c in result['chars'] if c['name'] == name)
                    self.assertEqual(char['values'][0]['value'], amount)
                    self.assertEqual(char['values'][0]['unit'], unit)
                    self.assertEqual(char['values'][0]['type'], 'number')
                    self.assertEqual(char['mapping_status'], 'mapped')
                    self.assertEqual([c['code'] for c in result['candidates']], selected)
                    self.assertFalse(result['unrecognized'])
                    if 'строительный' in query:
                        self.assertFalse(result['chars'][0]['in_ktru'])
        self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), before)

    def test_duplicate_catalogue_rows_survive_http_serialization(self):
        with sqlite3.connect(self.path) as db:
            original = db.execute("SELECT id FROM ktru_characteristic WHERE position_code='A'").fetchone()[0]
            duplicate = db.execute("INSERT INTO ktru_characteristic (position_code, name) VALUES ('A', 'Длина рукоятки')").lastrowid
            db.execute('''INSERT INTO ktru_characteristic_value
                (characteristic_id, min_value, max_value, min_notation, max_notation, okei_code)
                VALUES (?, 100, 150, 'greaterOrEqual', 'less', '003')''', (duplicate,))
        db.close()
        response = self.client.post('/extract', json={
            'normalized_query': 'ручка 10 см', 'candidate_codes': ['A']})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result['candidates'][0]['status'], 'matched')
        char = result['candidates'][0]['characteristics'][0]
        self.assertEqual(char['source_ids'], [original, duplicate])
        self.assertEqual(len(char['values']), 1)
        self.assertEqual([r['characteristic_id'] for r in result['chars'][0]['ktru_refs']], [original, duplicate])

    def test_reported_nylon_gloves_request_against_real_catalogue(self):
        path = Path(__file__).resolve().parents[2] / 'ktru.db'
        if not path.exists():
            self.skipTest('Реальный каталог отсутствует')
        before = hashlib.sha256(path.read_bytes()).digest()
        textile = [f'14.12.30.150-000000{i:02}' for i in [2, 3, 1, 4]]
        surgical = [f'22.19.60.111-000000{i:02}' for i in [1, 2, 3, 4, 6, 5]]
        payload = {'query': 'перчатки нейлон', 'canonical_query': 'перчатки нейлон',
                   'lemmatized_query': 'перчатка нейлон',
                   'candidates': [{'ktru_code': code, 'is_template': code.endswith('00000004'),
                                   'status': 'ACTIVE', 'rrf_score': 0.016} for code in textile + surgical]}
        with TestClient(create_app(db_path=path)) as client:
            response = client.post('/extract/from-search', json=payload)
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual([c['code'] for c in result['candidates']], textile)
            self.assertEqual([c['code'] for c in result['rejected_candidates']], surgical)
            self.assertTrue(all(c['status'] == 'matched' for c in result['candidates']))
            self.assertEqual(len(result['chars']), 1)
            char = result['chars'][0]
            self.assertEqual(char['mapping_status'], 'alternatives')
            self.assertEqual(char['match_mode'], 'any')
            self.assertEqual(char['values'][0]['value'], 'Нейлон')
            self.assertEqual(len(char['ktru_refs']), 8)
            self.assertIsNone(char['code'])
            self.assertFalse(result['unrecognized'])
            for c in result['candidates']:
                self.assertEqual(len(c['matches'][0]['matched_characteristic_ids']), 2)
                self.assertEqual(c['matches'][0]['match_mode'], 'any')
            schema = client.get('/openapi.json').json()
            self.assertIn('alternatives', schema['components']['schemas']['QueryCharacteristic']['properties']['mapping_status']['enum'])
        self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), before)


if __name__ == '__main__':
    unittest.main()
