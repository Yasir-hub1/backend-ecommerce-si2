"""POS API tests."""
from decimal import Decimal

from django.test import SimpleTestCase

from payments.models import PaymentMethod
from payments.services import validate_pos_payment


class POSPaymentPreviewTests(SimpleTestCase):
    def test_mixed_payment_change_calculation(self):
        payments = [
            {'method': PaymentMethod.CASH, 'amount': '30.00', 'received_amount': '50.00'},
            {'method': PaymentMethod.CARD_POS, 'amount': '70.00'},
        ]
        summary = validate_pos_payment(total_due=Decimal('100.00'), payments=payments)
        self.assertTrue(summary['valid'])
        self.assertEqual(summary['total_change'], Decimal('20.00'))

    def test_cash_exact_payment_has_no_change(self):
        payments = [
            {'method': PaymentMethod.CASH, 'amount': '100.00', 'received_amount': '100.00'},
        ]
        summary = validate_pos_payment(total_due=Decimal('100.00'), payments=payments)
        self.assertEqual(summary['total_change'], Decimal('0.00'))
