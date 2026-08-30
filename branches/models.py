"""
Geographic and branch models for FashionStore.
"""
from django.db import models
from django.core.validators import MinValueValidator
from core.models import TimeStampedModel


class City(TimeStampedModel):
    """City model for branch locations."""

    name = models.CharField('Nombre', max_length=100)
    department = models.CharField('Departamento', max_length=100)
    is_active = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'cities'
        verbose_name = 'Ciudad'
        verbose_name_plural = 'Ciudades'
        unique_together = [['name', 'department']]
        ordering = ['department', 'name']

    def __str__(self):
        return f"{self.name}, {self.department}"


class Branch(TimeStampedModel):
    """
    Branch/Store location model.

    Stores can accept reservations within their operating hours
    and have a limited number of fitting rooms.
    """

    code = models.CharField(
        'Código',
        max_length=10,
        unique=True,
        help_text='Código único de la sucursal (ej: SCZ-01)',
    )
    name = models.CharField('Nombre', max_length=120)

    city = models.ForeignKey(
        'City',
        on_delete=models.PROTECT,
        related_name='branches',
        verbose_name='Ciudad',
    )

    address = models.CharField('Dirección', max_length=200)

    # Coordinates for "nearest branch" feature
    latitude = models.DecimalField(
        'Latitud',
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        'Longitud',
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    phone = models.CharField('Teléfono', max_length=20)

    # Operating hours
    opens_at = models.TimeField('Hora de apertura')
    closes_at = models.TimeField('Hora de cierre')

    # Fitting room capacity (limits reservations per time slot)
    fitting_rooms = models.PositiveSmallIntegerField(
        'Probadores',
        default=3,
        validators=[MinValueValidator(1)],
        help_text='Número de probadores disponibles',
    )

    is_active = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'branches'
        verbose_name = 'Sucursal'
        verbose_name_plural = 'Sucursales'
        ordering = ['city__department', 'city__name', 'code']
        indexes = [
            models.Index(fields=['city', 'is_active']),
            models.Index(fields=['code']),
        ]

    def __str__(self):
        return f"{self.name} ({self.code}) - {self.city}"
