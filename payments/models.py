"""
Payment models for FashionStore.

Supports multiple payment methods including Stripe integration.
"""
import uuid
from django.db import models
from django.core.validators import MinValueValidator
from core.models import TimeStampedModel


class PaymentMethod:
    """Payment method constants."""
    CARD_ONLINE = 'CARD_ONLINE'
    CASH = 'CASH'
    CARD_POS = 'CARD_POS'
    QR = 'QR'
    TRANSFER = 'TRANSFER'

    CHOICES = [
        (CARD_ONLINE, 'Tarjeta en línea'),
        (CASH, 'Efectivo'),
        (CARD_POS, 'Tarjeta en POS'),
        (QR, 'QR'),
        (TRANSFER, 'Transferencia'),
    ]


class PaymentProvider:
    """Payment provider constants."""
    STRIPE = 'STRIPE'
    NONE = 'NONE'

    CHOICES = [
        (STRIPE, 'Stripe'),
        (NONE, 'Ninguno'),
    ]


class PaymentStatus:
    """Payment status constants."""
    PENDING = 'PENDING'
    SUCCEEDED = 'SUCCEEDED'
    FAILED = 'FAILED'
    REFUNDED = 'REFUNDED'

    CHOICES = [
        (PENDING, 'Pendiente'),
        (SUCCEEDED, 'Exitoso'),
        (FAILED, 'Fallido'),
        (REFUNDED, 'Reembolsado'),
    ]


class Payment(TimeStampedModel):
    """
    Payment record.

    An order can have multiple payments (e.g., partial payments, mixed methods).
    """

    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.PROTECT,
        related_name='payments',
        verbose_name='Orden',
    )

    method = models.CharField(
        'Método',
        max_length=20,
        choices=PaymentMethod.CHOICES,
    )

    provider = models.CharField(
        'Proveedor',
        max_length=20,
        choices=PaymentProvider.CHOICES,
        default=PaymentProvider.NONE,
    )

    status = models.CharField(
        'Estado',
        max_length=20,
        choices=PaymentStatus.CHOICES,
        default=PaymentStatus.PENDING,
        db_index=True,
    )

    amount = models.DecimalField(
        'Monto',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    # Stripe integration fields
    provider_payment_intent_id = models.CharField(
        'ID de PaymentIntent',
        max_length=64,
        unique=True,
        null=True,
        blank=True,
    )

    provider_charge_id = models.CharField(
        'ID de Charge',
        max_length=64,
        null=True,
        blank=True,
    )

    # Idempotency key for Stripe
    idempotency_key = models.UUIDField(
        'Clave de idempotencia',
        unique=True,
        default=uuid.uuid4,
    )

    # Cash payment fields
    received_amount = models.DecimalField(
        'Monto recibido',
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Solo para pagos en efectivo',
    )

    change_amount = models.DecimalField(
        'Cambio',
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Solo para pagos en efectivo',
    )

    # Raw response from payment provider (for debugging/audit)
    raw_response = models.JSONField(
        'Respuesta del proveedor',
        default=dict,
        blank=True,
    )

    paid_at = models.DateTimeField('Pagado en', null=True, blank=True)

    class Meta:
        db_table = 'payments'
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['provider_payment_intent_id']),
        ]

    def __str__(self):
        return f"{self.order.code} - {self.get_method_display()} - {self.amount}"


class StripeWebhookEvent(TimeStampedModel):
    """
    Stripe webhook event log.

    Ensures idempotency: each event_id is processed exactly once.
    """

    event_id = models.CharField(
        'ID del evento',
        max_length=64,
        unique=True,
        help_text='Stripe event ID',
    )

    event_type = models.CharField('Tipo de evento', max_length=64)

    payload = models.JSONField('Payload', default=dict)

    processed_at = models.DateTimeField(
        'Procesado en',
        null=True,
        blank=True,
        help_text='NULL hasta que se procese',
    )

    error = models.TextField('Error', blank=True)

    class Meta:
        db_table = 'stripe_webhook_events'
        verbose_name = 'Evento de Webhook Stripe'
        verbose_name_plural = 'Eventos de Webhook Stripe'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event_id']),
            models.Index(fields=['processed_at']),
        ]

    def __str__(self):
        status = "Procesado" if self.processed_at else "Pendiente"
        return f"{self.event_type} - {status}"


class Receipt(TimeStampedModel):
    """
    Sales receipt/invoice.

    Generated when order is paid.
    """

    order = models.OneToOneField(
        'orders.Order',
        on_delete=models.PROTECT,
        related_name='receipt',
        verbose_name='Orden',
    )

    # Sequential number per branch
    number = models.PositiveIntegerField('Número')

    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.PROTECT,
        related_name='receipts',
        verbose_name='Sucursal',
    )

    issued_at = models.DateTimeField('Emitido en', auto_now_add=True)

    # PDF file
    pdf_file = models.FileField(
        'Archivo PDF',
        upload_to='receipts/%Y/%m/',
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'receipts'
        verbose_name = 'Comprobante'
        verbose_name_plural = 'Comprobantes'
        ordering = ['-issued_at']
        unique_together = [['branch', 'number']]
        indexes = [
            models.Index(fields=['branch', '-number']),
        ]

    def __str__(self):
        return f"{self.branch.code}-{self.number:06d}"
