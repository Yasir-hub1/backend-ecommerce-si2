"""
Order and Cart models for FashionStore.

Unified order model for all channels: WEB, MOBILE, POS.
"""
import uuid
from django.db import models
from django.db.models import Q, F, CheckConstraint
from django.core.validators import MinValueValidator
from core.models import TimeStampedModel, CodeGeneratorMixin


# =============================================================================
# CART
# =============================================================================

class Cart(TimeStampedModel):
    """
    Shopping cart for customers.

    One active cart per customer.
    For guest users, uses session_key.
    """

    customer = models.OneToOneField(
        'accounts.CustomerProfile',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='cart',
        verbose_name='Cliente',
    )

    # For anonymous/guest users
    session_key = models.CharField(
        'Sesión',
        max_length=40,
        null=True,
        blank=True,
        unique=True,
        help_text='Clave de sesión para usuarios invitados',
    )

    class Meta:
        db_table = 'carts'
        verbose_name = 'Carrito'
        verbose_name_plural = 'Carritos'

    def __str__(self):
        if self.customer:
            return f"Carrito de {self.customer.user.get_full_name()}"
        return f"Carrito invitado ({self.session_key})"


class CartItem(TimeStampedModel):
    """
    Item in a shopping cart.

    ANTI-REDUNDANCY: Price is NOT stored here.
    The cart always reflects current prices.
    Price is frozen only when creating an Order.
    """

    cart = models.ForeignKey(
        'Cart',
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Carrito',
    )

    variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.PROTECT,
        related_name='cart_items',
        verbose_name='Variante',
    )

    quantity = models.PositiveIntegerField('Cantidad', default=1)

    class Meta:
        db_table = 'cart_items'
        verbose_name = 'Ítem de Carrito'
        verbose_name_plural = 'Ítems de Carrito'
        unique_together = [['cart', 'variant']]

    def __str__(self):
        return f"{self.variant.sku} x{self.quantity}"


# =============================================================================
# ORDER
# =============================================================================

class OrderChannel:
    """Order channel constants."""
    WEB = 'WEB'
    MOBILE = 'MOBILE'
    POS = 'POS'

    CHOICES = [
        (WEB, 'Web'),
        (MOBILE, 'Móvil'),
        (POS, 'Punto de Venta'),
    ]


class OrderStatus:
    """Order status constants."""
    PENDING_PAYMENT = 'PENDING_PAYMENT'
    PAID = 'PAID'
    PREPARING = 'PREPARING'
    READY = 'READY'
    DELIVERED = 'DELIVERED'
    CANCELLED = 'CANCELLED'
    REFUNDED = 'REFUNDED'

    CHOICES = [
        (PENDING_PAYMENT, 'Pendiente de pago'),
        (PAID, 'Pagado'),
        (PREPARING, 'Preparando'),
        (READY, 'Listo para retiro'),
        (DELIVERED, 'Entregado'),
        (CANCELLED, 'Cancelado'),
        (REFUNDED, 'Reembolsado'),
    ]


class Order(CodeGeneratorMixin, TimeStampedModel):
    """
    Unified order model for all sales channels.

    CRITICAL DESIGN DECISION:
    One Order model for WEB, MOBILE, and POS sales.
    This prevents duplicating inventory, payment, and report logic.

    Price denormalization (acceptable):
    - subtotal, tax_total, discount_total, grand_total are frozen
    - This is a fiscal document that must not change
    """
    code_prefix = 'ORD'
    code_length = 10

    code = models.CharField('Código', max_length=20, unique=True, editable=False)
    public_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)

    customer = models.ForeignKey(
        'accounts.CustomerProfile',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='orders',
        verbose_name='Cliente',
        help_text='NULL para ventas anónimas en mostrador',
    )

    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.PROTECT,
        related_name='orders',
        verbose_name='Sucursal',
        help_text='Sucursal que vende o entrega',
    )

    channel = models.CharField(
        'Canal',
        max_length=10,
        choices=OrderChannel.CHOICES,
    )

    # Link to reservation if order came from try-on
    reservation = models.ForeignKey(
        'reservations.Reservation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
        verbose_name='Reserva',
    )

    status = models.CharField(
        'Estado',
        max_length=20,
        choices=OrderStatus.CHOICES,
        default=OrderStatus.PENDING_PAYMENT,
        db_index=True,
    )

    # Frozen totals (fiscal document)
    subtotal = models.DecimalField(
        'Subtotal',
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    discount_total = models.DecimalField(
        'Descuento total',
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    tax_total = models.DecimalField(
        'Impuestos',
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    grand_total = models.DecimalField(
        'Total',
        max_digits=12,
        decimal_places=2,
    )

    currency = models.CharField('Moneda', max_length=3, default='BOB')

    # Promotion applied
    promotion = models.ForeignKey(
        'promotions.Promotion',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='orders',
        verbose_name='Promoción',
    )

    # POS: created by cashier
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='orders_created',
        verbose_name='Creado por',
    )

    paid_at = models.DateTimeField('Pagado en', null=True, blank=True)

    class Meta:
        db_table = 'orders'
        verbose_name = 'Orden'
        verbose_name_plural = 'Órdenes'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['branch', '-created_at']),
            models.Index(fields=['customer', '-created_at']),
            models.Index(fields=['status', 'channel']),
            models.Index(fields=['code']),
            models.Index(fields=['public_id']),
        ]
        constraints = [
            CheckConstraint(
                check=Q(grand_total__gte=0),
                name='order_total_non_negative'
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.get_channel_display()} - {self.branch.code}"

    @property
    def is_paid(self):
        """Check if order is fully paid."""
        # Import here to avoid circular import
        from payments.models import PaymentStatus

        if self.status in [OrderStatus.PAID, OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.DELIVERED]:
            return True

        # Calculate from payments
        total_paid = sum(
            payment.amount
            for payment in self.payments.filter(status=PaymentStatus.SUCCEEDED)
        )
        return total_paid >= self.grand_total


class OrderItem(TimeStampedModel):
    """
    Line item in an order.

    PRICE DENORMALIZATION (acceptable):
    - unit_price is frozen at time of sale
    - The catalog can change, but invoices must not
    - line_total is calculated (NOT stored)
    """

    order = models.ForeignKey(
        'Order',
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Orden',
    )

    variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.PROTECT,
        related_name='order_items',
        verbose_name='Variante',
    )

    quantity = models.PositiveIntegerField(
        'Cantidad',
        validators=[MinValueValidator(1)],
    )

    # Frozen price at time of sale
    unit_price = models.DecimalField(
        'Precio unitario',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Precio al momento de la venta',
    )

    discount_amount = models.DecimalField(
        'Descuento',
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    class Meta:
        db_table = 'order_items'
        verbose_name = 'Ítem de Orden'
        verbose_name_plural = 'Ítems de Orden'
        unique_together = [['order', 'variant']]

    def __str__(self):
        return f"{self.order.code} - {self.variant.sku} x{self.quantity}"

    @property
    def line_total(self):
        """Calculate line total (derived, not stored)."""
        return (self.unit_price * self.quantity) - self.discount_amount
