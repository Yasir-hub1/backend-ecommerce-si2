"""
Promotions and discounts models for FashionStore.
"""
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from core.models import TimeStampedModel


class DiscountType:
    """Discount type constants."""
    PERCENT = 'PERCENT'
    FIXED = 'FIXED'

    CHOICES = [
        (PERCENT, 'Porcentaje'),
        (FIXED, 'Monto fijo'),
    ]


class Promotion(TimeStampedModel):
    """
    Promotion/discount model.

    Can be applied automatically or via code.
    """

    name = models.CharField('Nombre', max_length=200)

    code = models.CharField(
        'Código',
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        help_text='Código de cupón (NULL para promociones automáticas)',
    )

    discount_type = models.CharField(
        'Tipo de descuento',
        max_length=10,
        choices=DiscountType.CHOICES,
    )

    value = models.DecimalField(
        'Valor',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Porcentaje (0-100) o monto fijo',
    )

    starts_at = models.DateTimeField('Inicia en')
    ends_at = models.DateTimeField('Termina en')

    min_order_amount = models.DecimalField(
        'Monto mínimo de orden',
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )

    max_uses = models.PositiveIntegerField(
        'Usos máximos',
        null=True,
        blank=True,
        help_text='NULL para ilimitado',
    )

    used_count = models.PositiveIntegerField('Veces usado', default=0)

    # Optional scope filters (M2M)
    categories = models.ManyToManyField(
        'catalog.Category',
        blank=True,
        related_name='promotions',
        verbose_name='Categorías',
        help_text='Vacío = aplica a todas',
    )

    collections = models.ManyToManyField(
        'catalog.Collection',
        blank=True,
        related_name='promotions',
        verbose_name='Colecciones',
        help_text='Vacío = aplica a todas',
    )

    products = models.ManyToManyField(
        'catalog.Product',
        blank=True,
        related_name='promotions',
        verbose_name='Productos',
        help_text='Vacío = aplica a todos',
    )

    is_active = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'promotions'
        verbose_name = 'Promoción'
        verbose_name_plural = 'Promociones'
        ordering = ['-starts_at']

    def __str__(self):
        return self.name
