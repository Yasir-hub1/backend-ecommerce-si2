"""
Inventory models for FashionStore.

Implements a dual-system:
- BranchStock: transactional cache (current stock levels)
- InventoryMovement: append-only ledger (historical truth)
"""
from django.db import models
from django.db.models import Q, F, CheckConstraint
from django.core.validators import MinValueValidator
from core.models import TimeStampedModel


class BranchStock(TimeStampedModel):
    """
    Current stock levels per branch and variant.

    This is a CACHE derived from InventoryMovement.
    Use inventory.services.apply_movements() to modify it.

    ANTI-REDUNDANCY RULES:
    - on_hand >= 0 (check constraint)
    - reserved >= 0 (check constraint)
    - reserved <= on_hand (check constraint)
    - available = on_hand - reserved (property, NOT stored)
    """

    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.PROTECT,
        related_name='stock',
        verbose_name='Sucursal',
    )

    variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.PROTECT,
        related_name='branch_stocks',
        verbose_name='Variante',
    )

    on_hand = models.PositiveIntegerField(
        'En mano',
        default=0,
        help_text='Unidades físicas en tienda',
    )

    reserved = models.PositiveIntegerField(
        'Reservado',
        default=0,
        help_text='Unidades comprometidas por reservas activas',
    )

    min_threshold = models.PositiveIntegerField(
        'Umbral mínimo',
        default=0,
        help_text='Alerta de reposición',
    )

    class Meta:
        db_table = 'branch_stock'
        verbose_name = 'Stock por Sucursal'
        verbose_name_plural = 'Stock por Sucursal'
        unique_together = [['branch', 'variant']]
        indexes = [
            models.Index(fields=['branch', 'variant']),
            models.Index(fields=['variant', 'branch']),
        ]
        constraints = [
            CheckConstraint(
                check=Q(on_hand__gte=0),
                name='stock_on_hand_non_negative'
            ),
            CheckConstraint(
                check=Q(reserved__gte=0),
                name='stock_reserved_non_negative'
            ),
            CheckConstraint(
                check=Q(reserved__lte=F('on_hand')),
                name='stock_reserved_lte_on_hand'
            ),
        ]

    def __str__(self):
        return f"{self.branch.code} - {self.variant.sku}: {self.on_hand} (reserv: {self.reserved})"

    @property
    def available(self):
        """Available units = on_hand - reserved."""
        return self.on_hand - self.reserved


class MovementType:
    """Inventory movement type constants."""

    # Incoming
    IN_RECEIPT = 'IN_RECEIPT'
    RETURN_IN = 'RETURN_IN'
    ADJUST_IN = 'ADJUST_IN'
    TRANSFER_IN = 'TRANSFER_IN'

    # Reservation
    RESERVE_HOLD = 'RESERVE_HOLD'
    RESERVE_RELEASE = 'RESERVE_RELEASE'

    # Outgoing
    OUT_SALE = 'OUT_SALE'
    OUT_SALE_RESERVED = 'OUT_SALE_RESERVED'
    ADJUST_OUT = 'ADJUST_OUT'
    TRANSFER_OUT = 'TRANSFER_OUT'

    CHOICES = [
        (IN_RECEIPT, 'Recepción de proveedor'),
        (RETURN_IN, 'Devolución de cliente'),
        (ADJUST_IN, 'Ajuste positivo'),
        (TRANSFER_IN, 'Transferencia entrante'),
        (RESERVE_HOLD, 'Reserva (bloqueo)'),
        (RESERVE_RELEASE, 'Liberación de reserva'),
        (OUT_SALE, 'Venta'),
        (OUT_SALE_RESERVED, 'Venta de reserva'),
        (ADJUST_OUT, 'Ajuste negativo'),
        (TRANSFER_OUT, 'Transferencia saliente'),
    ]


class ReferenceType:
    """Reference type for movements."""
    RESERVATION = 'RESERVATION'
    ORDER = 'ORDER'
    RECEIPT = 'RECEIPT'
    MANUAL = 'MANUAL'
    TRANSFER = 'TRANSFER'

    CHOICES = [
        (RESERVATION, 'Reserva'),
        (ORDER, 'Orden'),
        (RECEIPT, 'Recepción'),
        (MANUAL, 'Manual'),
        (TRANSFER, 'Transferencia'),
    ]


class InventoryMovement(TimeStampedModel):
    """
    Inventory movement ledger (append-only).

    This is the SOURCE OF TRUTH for inventory.
    BranchStock is derived from this by summing movements.

    IMPORTANT:
    - Never UPDATE or DELETE movements
    - Always create a new offsetting movement to correct errors
    - Use inventory.services.apply_movements() to ensure consistency
    """

    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.PROTECT,
        related_name='inventory_movements',
        verbose_name='Sucursal',
    )

    variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.PROTECT,
        related_name='inventory_movements',
        verbose_name='Variante',
    )

    movement_type = models.CharField(
        'Tipo de movimiento',
        max_length=20,
        choices=MovementType.CHOICES,
    )

    quantity = models.PositiveIntegerField(
        'Cantidad',
        validators=[MinValueValidator(1)],
        help_text='Siempre positivo; el signo lo da el tipo',
    )

    reference_type = models.CharField(
        'Tipo de referencia',
        max_length=20,
        choices=ReferenceType.CHOICES,
    )

    reference_id = models.BigIntegerField(
        'ID de referencia',
        null=True,
        blank=True,
        help_text='ID del documento origen (Reservation, Order, etc)',
    )

    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='inventory_movements_created',
        verbose_name='Creado por',
    )

    note = models.CharField('Nota', max_length=200, blank=True)

    class Meta:
        db_table = 'inventory_movements'
        verbose_name = 'Movimiento de Inventario'
        verbose_name_plural = 'Movimientos de Inventario'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['branch', 'created_at']),
            models.Index(fields=['variant', 'created_at']),
            models.Index(fields=['reference_type', 'reference_id']),
        ]
        constraints = [
            CheckConstraint(
                check=Q(quantity__gt=0),
                name='movement_qty_positive'
            ),
        ]

    def __str__(self):
        return f"{self.get_movement_type_display()} - {self.variant.sku} x{self.quantity}"

    def save(self, *args, **kwargs):
        """
        Prevent UPDATE operations on movements.
        Only creation is allowed.
        """
        if self.pk is not None:
            raise ValueError(
                "Inventory movements are append-only. Create a new offsetting movement instead."
            )
        super().save(*args, **kwargs)
