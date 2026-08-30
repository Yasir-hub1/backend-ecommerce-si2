"""
Notification models for FashionStore.
"""
from django.db import models
from core.models import TimeStampedModel


class NotificationType:
    """Notification type constants."""
    RESERVATION_CREATED = 'RESERVATION_CREATED'
    RESERVATION_READY = 'RESERVATION_READY'
    ORDER_CONFIRMED = 'ORDER_CONFIRMED'
    ORDER_READY = 'ORDER_READY'
    LOW_STOCK_ALERT = 'LOW_STOCK_ALERT'

    CHOICES = [
        (RESERVATION_CREATED, 'Reserva creada'),
        (RESERVATION_READY, 'Reserva lista'),
        (ORDER_CONFIRMED, 'Orden confirmada'),
        (ORDER_READY, 'Orden lista para retiro'),
        (LOW_STOCK_ALERT, 'Alerta de stock bajo'),
    ]


class Notification(TimeStampedModel):
    """
    Notification model for users and branches.
    """

    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
        verbose_name='Usuario',
    )

    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
        verbose_name='Sucursal',
    )

    notification_type = models.CharField(
        'Tipo',
        max_length=30,
        choices=NotificationType.CHOICES,
    )

    title = models.CharField('Título', max_length=200)
    message = models.TextField('Mensaje')

    # Optional reference to related object
    reference_type = models.CharField('Tipo de referencia', max_length=30, blank=True)
    reference_id = models.BigIntegerField('ID de referencia', null=True, blank=True)

    is_read = models.BooleanField('Leído', default=False)
    sent_via_email = models.BooleanField('Enviado por email', default=False)

    class Meta:
        db_table = 'notifications'
        verbose_name = 'Notificación'
        verbose_name_plural = 'Notificaciones'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
            models.Index(fields=['branch', 'is_read', '-created_at']),
        ]

    def __str__(self):
        return f"{self.title} - {self.user or self.branch}"
