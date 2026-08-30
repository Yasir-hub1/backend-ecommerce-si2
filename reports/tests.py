from datetime import date

from django.test import SimpleTestCase, TestCase

from reports.prompt_interpreter import InterpretedReportSpec, interpret_prompt
from reports.services import render_generative_report


class PromptInterpreterTests(SimpleTestCase):
    def test_sales_and_best_product_prompt(self):
        spec = interpret_prompt(
            prompt='quiero un reporte de todas las ventas incluyendo qué producto es el mejor',
            today=date(2026, 8, 29),
        )
        self.assertTrue(spec.include_sales)
        self.assertTrue(spec.include_sales_detail)
        self.assertTrue(spec.include_top_products)
        self.assertEqual(spec.product_ranking, 'best')
        self.assertFalse(spec.include_reservations)
        self.assertFalse(spec.include_inventory)

    def test_least_sold_product_prompt(self):
        spec = interpret_prompt(
            prompt='quiero saber que producto se vende menos',
            today=date(2026, 8, 29),
        )
        self.assertTrue(spec.include_top_products)
        self.assertEqual(spec.product_ranking, 'worst')
        self.assertFalse(spec.include_sales)
        self.assertFalse(spec.include_reservations)
        self.assertFalse(spec.include_inventory)

    def test_last_week_date_range(self):
        spec = interpret_prompt(
            prompt='ventas de la última semana',
            today=date(2026, 8, 29),
        )
        self.assertEqual(spec.date_from, date(2026, 8, 22))
        self.assertEqual(spec.date_to, date(2026, 8, 29))
        self.assertEqual(spec.period_label, 'Últimos 7 días')


class PromptInterpreterBranchTests(TestCase):
    def test_inventory_only_prompt(self):
        spec = interpret_prompt(
            prompt='muéstrame inventario y stock bajo de la sucursal',
            today=date(2026, 8, 29),
        )
        self.assertTrue(spec.include_inventory)
        self.assertTrue(spec.include_low_stock)
        self.assertFalse(spec.include_sales)
        self.assertFalse(spec.include_reservations)


class ReportRendererTests(SimpleTestCase):
    def test_render_omits_unrequested_sections(self):
        spec = InterpretedReportSpec(
            include_sales=True,
            include_sales_detail=False,
            include_top_products=True,
            product_ranking='best',
            include_reservations=False,
            include_inventory=False,
            include_low_stock=False,
            date_from=None,
            date_to=None,
            branch_id=None,
            top_limit=5,
            sales_detail_limit=0,
            period_label='Histórico completo',
            scope_label='Todas las sucursales',
        )
        payload = {
            'sales': {'total_sales': '100.00', 'order_count': 2, 'orders': []},
            'top_products': [
                {'product_name': 'Camisa', 'units_sold': 3, 'revenue': '90.00'},
            ],
        }
        text = render_generative_report(prompt='ventas y mejor producto', spec=spec, payload=payload)
        self.assertIn('Ventas:', text)
        self.assertIn('Ranking de productos:', text)
        self.assertNotIn('Reservas:', text)
        self.assertNotIn('Inventario:', text)

    def test_render_worst_product_highlight(self):
        spec = InterpretedReportSpec(
            include_sales=False,
            include_sales_detail=False,
            include_top_products=True,
            product_ranking='worst',
            include_reservations=False,
            include_inventory=False,
            include_low_stock=False,
            date_from=None,
            date_to=None,
            branch_id=None,
            top_limit=5,
            sales_detail_limit=0,
            period_label='Histórico completo',
            scope_label='Todas las sucursales',
        )
        payload = {
            'sales_context': {'total_sales': '3603.57', 'order_count': 7},
            'product_ranking': 'worst',
            'top_products': [
                {'product_name': 'Falda Plisada Escolar', 'units_sold': 1, 'revenue': '180.00'},
                {'product_name': 'Camisa Oxford Slim', 'units_sold': 1, 'revenue': '289.00'},
            ],
        }
        text = render_generative_report(
            prompt='quiero saber que producto se vende menos',
            spec=spec,
            payload=payload,
        )
        self.assertNotIn('Ventas:', text)
        self.assertIn('Productos con menor venta:', text)
        self.assertIn('Producto menos vendido del periodo: Falda Plisada Escolar', text)
        self.assertNotIn('Mejor producto del periodo', text)
