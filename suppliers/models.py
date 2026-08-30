"""
Supplier and procurement models for FashionStore.
"""
from django.db import models
from django.core.validators import MinValueValidator
from core.models import TimeStampedModel, CodeGeneratorMixin


class Supplier(TimeStampedModel):
    """
    Supplier/vendor model.

    Suppliers can optionally have a User account for the supplier portal.
    """

    legal_name = models.CharField('Razón Social', max_length=200)
    trade_name = models.CharField('Nombre Comercial', max_length=200, blank=True)

    tax_id = models.CharField(
        'NIT',
        max_length=50,
        unique=True,
        help_text='Número de Identificación Tributaria',
    )

    email = models.EmailField('Correo electrónico')
    phone = models.CharField('Teléfono', max_length=20)
    address = models.CharField('Dirección', max_length=300, blank=True)

    # Optional user account for supplier portal access
    user = models.OneToOneField(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supplier',
        verbose_name='Usuario del portal',
    )

    is_active = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'suppliers'
        verbose_name = 'Proveedor'
        verbose_name_plural = 'Proveedores'
        ordering = ['legal_name']

    def __str__(self):
        return self.trade_name or self.legal_name


class PurchaseReceiptStatus:
    """Purchase receipt status constants."""
    DRAFT = 'DRAFT'
    CONFIRMED = 'CONFIRMED'
    CANCELLED = 'CANCELLED'

    CHOICES = [
        (DRAFT, 'Borrador'),
        (CONFIRMED, 'Confirmado'),
        (CANCELLED, 'Cancelado'),
    ]


class PurchaseReceipt(CodeGeneratorMixin, TimeStampedModel):
    """
    Purchase receipt / goods receiving.

    When confirmed, creates inventory movements (IN_RECEIPT).
    """
    code_prefix = 'RCV'
    code_length = 8

    code = models.CharField('Código', max_length=14, unique=True, editable=False)

    supplier = models.ForeignKey(
        'Supplier',
        on_delete=models.PROTECT,
        related_name='receipts',
        verbose_name='Proveedor',
    )

    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.PROTECT,
        related_name='purchase_receipts',
        verbose_name='Sucursal',
        help_text='Sucursal que recibe la mercadería',
    )

    status = models.CharField(
        'Estado',
        max_length=20,
        choices=PurchaseReceiptStatus.CHOICES,
        default=PurchaseReceiptStatus.DRAFT,
    )

    received_at = models.DateTimeField('Fecha de recepción', null=True, blank=True)

    received_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='receipts_received',
        verbose_name='Recibido por',
    )

    invoice_number = models.CharField(
        'Número de factura',
        max_length=50,
        blank=True,
    )

    notes = models.TextField('Notas', blank=True)

    class Meta:
        db_table = 'purchase_receipts'
        verbose_name = 'Recepción de Compra'
        verbose_name_plural = 'Recepciones de Compra'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['branch', 'status']),
            models.Index(fields=['supplier']),
        ]

    def __str__(self):
        return f"{self.code} - {self.supplier.trade_name or self.supplier.legal_name}"


class PurchaseReceiptItem(TimeStampedModel):
    """Line item in a purchase receipt."""

    receipt = models.ForeignKey(
        'PurchaseReceipt',
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Recepción',
    )

    variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.PROTECT,
        related_name='receipt_items',
        verbose_name='Variante',
    )

    quantity = models.PositiveIntegerField(
        'Cantidad',
        validators=[MinValueValidator(1)],
    )

    unit_cost = models.DecimalField(
        'Costo unitario',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        db_table = 'purchase_receipt_items'
        verbose_name = 'Ítem de Recepción'
        verbose_name_plural = 'Ítems de Recepción'
        unique_together = [['receipt', 'variant']]

    def __str__(self):
        return f"{self.variant} - {self.quantity} unidades"

    @property
    def line_total(self):
        """Calculate line total."""
        return self.quantity * self.unit_cost


class ProductSubmissionStatus:
    PENDING = 'PENDING'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'

    CHOICES = [
        (PENDING, 'Pendiente'),
        (APPROVED, 'Aprobado'),
        (REJECTED, 'Rechazado'),
    ]


class ProductSubmission(TimeStampedModel):
    """Supplier proposal for a new catalog product."""

    supplier = models.ForeignKey(
        'Supplier',
        on_delete=models.CASCADE,
        related_name='product_submissions',
        verbose_name='Proveedor',
    )
    name = models.CharField('Nombre', max_length=200)
    description = models.TextField('Descripción', blank=True)
    collection = models.ForeignKey(
        'catalog.Collection',
        on_delete=models.PROTECT,
        related_name='product_submissions',
        verbose_name='Colección',
    )
    gender = models.CharField('Género', max_length=10)
    base_price = models.DecimalField(
        'Precio base',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    material = models.CharField('Material', max_length=200, blank=True)
    status = models.CharField(
        'Estado',
        max_length=20,
        choices=ProductSubmissionStatus.CHOICES,
        default=ProductSubmissionStatus.PENDING,
        db_index=True,
    )
    review_notes = models.TextField('Notas de revisión', blank=True)

    class Meta:
        db_table = 'product_submissions'
        verbose_name = 'Propuesta de producto'
        verbose_name_plural = 'Propuestas de producto'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.get_status_display()})'
