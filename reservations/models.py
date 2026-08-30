"""
Reservation models for FashionStore.

Allows customers to reserve products for in-store try-on.
"""
from django.db import models
from django.db.models import Q, F, CheckConstraint
from django.utils import timezone
from core.models import TimeStampedModel, CodeGeneratorMixin


class ReservationStatus:
    """Reservation status constants."""
    PENDING = 'PENDING'
    PREPARING = 'PREPARING'
    READY = 'READY'
    IN_FITTING = 'IN_FITTING'
    COMPLETED = 'COMPLETED'
    CANCELLED = 'CANCELLED'
    EXPIRED = 'EXPIRED'
    NO_SHOW = 'NO_SHOW'

    CHOICES = [
        (PENDING, 'Pendiente'),
        (PREPARING, 'Preparando'),
        (READY, 'Listo para probador'),
        (IN_FITTING, 'En probador'),
        (COMPLETED, 'Completado'),
        (CANCELLED, 'Cancelado'),
        (EXPIRED, 'Expirado'),
        (NO_SHOW, 'No se presentó'),
    ]

    # Valid state transitions
    TRANSITIONS = {
        PENDING: [PREPARING, CANCELLED, EXPIRED],
        PREPARING: [READY, CANCELLED],
        READY: [IN_FITTING, NO_SHOW, CANCELLED],
        IN_FITTING: [COMPLETED],
    }


class Reservation(CodeGeneratorMixin, TimeStampedModel):
    """
    Customer reservation for in-store try-on.

    Workflow:
    1. Customer reserves items online for a specific branch/time
    2. Stock is marked as RESERVED (not decremented)
    3. Branch staff prepares items: PENDING → PREPARING → READY
    4. Customer arrives and tries on: READY → IN_FITTING
    5. Customer purchases some/all items: IN_FITTING → COMPLETED
    6. Purchased items: OUT_SALE_RESERVED movement
    7. Non-purchased items: RESERVE_RELEASE movement
    """
    code_prefix = 'RSV'
    code_length = 8

    code = models.CharField('Código', max_length=14, unique=True, editable=False)

    customer = models.ForeignKey(
        'accounts.CustomerProfile',
        on_delete=models.PROTECT,
        related_name='reservations',
        verbose_name='Cliente',
    )

    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.PROTECT,
        related_name='reservations',
        verbose_name='Sucursal',
    )

    scheduled_for = models.DateTimeField(
        'Programado para',
        help_text='Horario aproximado elegido por el cliente',
    )

    expires_at = models.DateTimeField(
        'Expira en',
        help_text='Fecha límite para completar la reserva',
    )

    status = models.CharField(
        'Estado',
        max_length=20,
        choices=ReservationStatus.CHOICES,
        default=ReservationStatus.PENDING,
        db_index=True,
    )

    notes = models.CharField('Notas', max_length=300, blank=True)

    # Branch staff who prepared the reservation
    prepared_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reservations_prepared',
        verbose_name='Preparado por',
    )

    class Meta:
        db_table = 'reservations'
        verbose_name = 'Reserva'
        verbose_name_plural = 'Reservas'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['branch', 'status', 'scheduled_for']),
            models.Index(fields=['customer', '-created_at']),
            models.Index(fields=['status', 'expires_at']),
            models.Index(fields=['code']),
        ]
        constraints = [
            CheckConstraint(
                check=Q(expires_at__gt=F('created_at')),
                name='reservation_expiry_valid'
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.customer.user.get_full_name()} - {self.branch.code}"

    @property
    def is_expired(self):
        """Check if reservation has expired."""
        return timezone.now() > self.expires_at and self.status in [
            ReservationStatus.PENDING,
            ReservationStatus.PREPARING,
            ReservationStatus.READY
        ]


class ItemStatus:
    """Reservation item status constants."""
    HELD = 'HELD'
    TRIED = 'TRIED'
    PURCHASED = 'PURCHASED'
    RETURNED_TO_FLOOR = 'RETURNED_TO_FLOOR'

    CHOICES = [
        (HELD, 'Reservado'),
        (TRIED, 'Probado'),
        (PURCHASED, 'Comprado'),
        (RETURNED_TO_FLOOR, 'Devuelto al piso'),
    ]


class ReservationItem(TimeStampedModel):
    """
    Line item in a reservation.

    Tracks individual items and their status through the try-on process.
    """

    reservation = models.ForeignKey(
        'Reservation',
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Reserva',
    )

    variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.PROTECT,
        related_name='reservation_items',
        verbose_name='Variante',
    )

    quantity = models.PositiveIntegerField('Cantidad', default=1)

    item_status = models.CharField(
        'Estado del ítem',
        max_length=20,
        choices=ItemStatus.CHOICES,
        default=ItemStatus.HELD,
    )

    class Meta:
        db_table = 'reservation_items'
        verbose_name = 'Ítem de Reserva'
        verbose_name_plural = 'Ítems de Reserva'
        unique_together = [['reservation', 'variant']]

    def __str__(self):
        return f"{self.reservation.code} - {self.variant.sku} x{self.quantity}"
