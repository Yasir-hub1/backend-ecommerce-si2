"""Lightweight tests for chat intent parsing (no DB required for unit bits)."""
from decimal import Decimal

from django.test import SimpleTestCase

from ai.intent import merge_intents, parse_intent


class IntentParseTests(SimpleTestCase):
    def test_office_look_detects_categories(self):
        intent = parse_intent('¿Qué me recomiendas para oficina?')
        self.assertIn('camisas', intent.category_slugs)
        self.assertIn('pantalones', intent.category_slugs)
        self.assertIn('oficina', intent.occasions)

    def test_color_and_casual(self):
        intent = parse_intent('Busco algo casual en negro')
        self.assertIn('Negro', intent.color_names)
        self.assertIn('poleras', intent.category_slugs)

    def test_price_ceiling(self):
        intent = parse_intent('poleras hasta 150 bs')
        self.assertEqual(intent.max_price, Decimal('150'))
        self.assertIn('poleras', intent.category_slugs)

    def test_merge_keeps_color_on_refinement(self):
        first = parse_intent('camisas negras')
        second = parse_intent('las más baratas')
        merged = merge_intents(first, second)
        self.assertIn('Negro', merged.color_names)
        self.assertEqual(merged.sort, 'price_asc')
