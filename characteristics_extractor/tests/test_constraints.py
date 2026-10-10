import unittest

from characteristics_extractor.constraints import numeric_range_spans


class NumericRangeTests(unittest.TestCase):
    def test_range_notations_preserve_original_spans(self):
        for fragment in (
            "100-120 см", "100–120 см", "100 — 120 см", "100-120см",
            "от 100 до 120 см", "от 100 см до 120 см", "100см-120см",
            "1,5–2,5 кг", "1.5-2.5 кг", "-20–-10 °C", "от −20 до −10 °C",
            "100-120", "ОТ 100 ДО 120 СМ",
        ):
            with self.subTest(fragment=fragment):
                query = f"🔨 Молоток {fragment}, масса 500 г"
                spans = numeric_range_spans(query)
                self.assertEqual(len(spans), 1)
                self.assertEqual(query[spans[0].start:spans[0].end], fragment)

    def test_scalar_dimensions_and_product_codes_are_not_intervals(self):
        for query in (
            "Молоток 15 см", "температура -20 °C", "габариты 100x120 мм",
            "габариты 100×120 мм", "модель МП-100-120", "модель AB100-120",
            "дата 2026-10-11", "код 25.73.30.141-00000001",
            "Молоток 100 см, рукоятка 120 см",
        ):
            with self.subTest(query=query):
                self.assertEqual(numeric_range_spans(query), [])
