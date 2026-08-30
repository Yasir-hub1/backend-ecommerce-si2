"""
Catalog models for FashionStore.

Implements the product catalog with:
- Categories (hierarchical)
- Brands
- Sizes (grouped by type)
- Colors
- Seasons and Collections
- Products and ProductVariants (the SKU)
- Product Images and AR Assets
"""
import uuid
from django.db import models
from django.core.validators import RegexValidator, MinValueValidator
from django.utils.text import slugify
from core.models import TimeStampedModel


# =============================================================================
# CATEGORY
# =============================================================================

class Category(TimeStampedModel):
    """
    Hierarchical product category.

    Examples: Ropa > Camisas > Camisas Formales
    """
    name = models.CharField('Nombre', max_length=100)
    slug = models.SlugField('Slug', max_length=120, unique=True)

    parent = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='Categoría padre',
    )

    size_group = models.ForeignKey(
        'SizeGroup',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='categories',
        verbose_name='Grupo de tallas',
        help_text='Grupo de tallas válido para esta categoría',
    )

    display_order = models.PositiveIntegerField('Orden', default=0)
    is_active = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'categories'
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'
        ordering = ['display_order', 'name']
        indexes = [
            models.Index(fields=['parent', 'is_active']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# =============================================================================
# BRAND
# =============================================================================

class Brand(TimeStampedModel):
    """Product brand."""

    name = models.CharField('Nombre', max_length=100, unique=True)
    slug = models.SlugField('Slug', max_length=120, unique=True)
    logo = models.ImageField('Logo', upload_to='brands/', blank=True, null=True)

    class Meta:
        db_table = 'brands'
        verbose_name = 'Marca'
        verbose_name_plural = 'Marcas'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# =============================================================================
# SIZE
# =============================================================================

class SizeGroup(models.Model):
    """
    Size group type.

    Different products use different size systems:
    - ALPHA_TOP: S, M, L, XL (tops)
    - WAIST_NUM: 28, 30, 32, 34 (pants)
    - SHOE_EU: 38, 39, 40, 41 (shoes)
    """

    ALPHA_TOP = 'ALPHA_TOP'
    ALPHA_BOTTOM = 'ALPHA_BOTTOM'
    WAIST_NUM = 'WAIST_NUM'
    SHOE_EU = 'SHOE_EU'
    SHOE_US = 'SHOE_US'
    NUMERIC = 'NUMERIC'

    TYPE_CHOICES = [
        (ALPHA_TOP, 'Alfa Superior (S/M/L/XL)'),
        (ALPHA_BOTTOM, 'Alfa Inferior (S/M/L/XL)'),
        (WAIST_NUM, 'Cintura Numérica (28/30/32)'),
        (SHOE_EU, 'Calzado EU (38/39/40)'),
        (SHOE_US, 'Calzado US (7/8/9)'),
        (NUMERIC, 'Numérico General'),
    ]

    name = models.CharField('Nombre', max_length=50, unique=True)
    description = models.CharField('Descripción', max_length=200, blank=True)

    class Meta:
        db_table = 'size_groups'
        verbose_name = 'Grupo de Tallas'
        verbose_name_plural = 'Grupos de Tallas'
        ordering = ['name']

    def __str__(self):
        return self.name


class Size(models.Model):
    """
    Individual size within a size group.

    Examples:
    - (ALPHA_TOP, 'M')
    - (WAIST_NUM, '32')
    - (SHOE_EU, '40')
    """

    group = models.ForeignKey(
        'SizeGroup',
        on_delete=models.PROTECT,
        related_name='sizes',
        verbose_name='Grupo',
    )

    code = models.CharField(
        'Código',
        max_length=10,
        help_text='Código de la talla (ej: M, 32, 40)',
    )

    display_order = models.PositiveIntegerField('Orden', default=0)

    class Meta:
        db_table = 'sizes'
        verbose_name = 'Talla'
        verbose_name_plural = 'Tallas'
        unique_together = [['group', 'code']]
        ordering = ['group', 'display_order', 'code']

    def __str__(self):
        return f"{self.group.name}: {self.code}"


# =============================================================================
# COLOR
# =============================================================================

class Color(TimeStampedModel):
    """Product color."""

    name = models.CharField('Nombre', max_length=50, unique=True)
    slug = models.SlugField('Slug', max_length=60, unique=True)

    hex_code_validator = RegexValidator(
        regex=r'^#[0-9A-Fa-f]{6}$',
        message='Código hexadecimal inválido. Use el formato #RRGGBB',
    )
    hex_code = models.CharField(
        'Código Hexadecimal',
        max_length=7,
        validators=[hex_code_validator],
        help_text='Código de color en formato #RRGGBB',
    )

    class Meta:
        db_table = 'colors'
        verbose_name = 'Color'
        verbose_name_plural = 'Colores'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# =============================================================================
# SEASON & COLLECTION
# =============================================================================

class Season(TimeStampedModel):
    """
    Fashion season.

    Examples:
    - Primavera-Verano 2026 (PV26)
    - Otoño-Invierno 2026 (OI26)
    """

    SPRING_SUMMER = 'SPRING_SUMMER'
    AUTUMN_WINTER = 'AUTUMN_WINTER'
    SCHOOL = 'SCHOOL'
    PROMO = 'PROMO'
    NEW_COLLECTION = 'NEW_COLLECTION'

    KIND_CHOICES = [
        (SPRING_SUMMER, 'Primavera-Verano'),
        (AUTUMN_WINTER, 'Otoño-Invierno'),
        (SCHOOL, 'Escolar'),
        (PROMO, 'Promocional'),
        (NEW_COLLECTION, 'Nueva Colección'),
    ]

    name = models.CharField('Nombre', max_length=100)
    code = models.CharField('Código', max_length=20, unique=True)
    kind = models.CharField('Tipo', max_length=20, choices=KIND_CHOICES)

    starts_on = models.DateField('Fecha de inicio')
    ends_on = models.DateField('Fecha de fin')

    is_active = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'seasons'
        verbose_name = 'Temporada'
        verbose_name_plural = 'Temporadas'
        ordering = ['-starts_on']

    def __str__(self):
        return f"{self.name} ({self.code})"


class Collection(TimeStampedModel):
    """
    Product collection within a season.

    Collections group products from the same supplier/brand campaign.
    """

    name = models.CharField('Nombre', max_length=120)
    slug = models.SlugField('Slug', max_length=140, unique=True)

    season = models.ForeignKey(
        'Season',
        on_delete=models.PROTECT,
        related_name='collections',
        verbose_name='Temporada',
    )

    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='collections',
        verbose_name='Proveedor',
    )

    launch_date = models.DateField('Fecha de lanzamiento', null=True, blank=True)
    is_active = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'collections'
        verbose_name = 'Colección'
        verbose_name_plural = 'Colecciones'
        ordering = ['-launch_date']

    def __str__(self):
        return f"{self.name} - {self.season.code}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# =============================================================================
# PRODUCT & VARIANT
# =============================================================================

class Product(TimeStampedModel):
    """
    Product master record.

    A product has multiple variants (size × color combinations).
    Stock, pricing overrides, and SKUs live in ProductVariant.
    """

    MALE = 'MALE'
    FEMALE = 'FEMALE'
    UNISEX = 'UNISEX'
    KIDS = 'KIDS'

    GENDER_CHOICES = [
        (MALE, 'Masculino'),
        (FEMALE, 'Femenino'),
        (UNISEX, 'Unisex'),
        (KIDS, 'Niños'),
    ]

    # Public ID for URLs (never expose primary key)
    public_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)

    name = models.CharField('Nombre', max_length=200)
    slug = models.SlugField('Slug', max_length=220, unique=True)
    description = models.TextField('Descripción', blank=True)

    category = models.ForeignKey(
        'Category',
        on_delete=models.PROTECT,
        related_name='products',
        verbose_name='Categoría',
    )

    brand = models.ForeignKey(
        'Brand',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='products',
        verbose_name='Marca',
    )

    # Season comes from collection
    collection = models.ForeignKey(
        'Collection',
        on_delete=models.PROTECT,
        related_name='products',
        verbose_name='Colección',
    )

    gender = models.CharField('Género', max_length=10, choices=GENDER_CHOICES)

    # Base price (variants can override)
    base_price = models.DecimalField(
        'Precio base',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    # Optional fields for chatbot
    care_instructions = models.CharField(
        'Instrucciones de cuidado',
        max_length=500,
        blank=True,
    )
    material = models.CharField('Material', max_length=200, blank=True)

    is_active = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'products'
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['collection']),
            models.Index(fields=['slug']),
            models.Index(fields=['public_id']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class ProductVariant(TimeStampedModel):
    """
    Product variant = Product × Size × Color = SKU.

    This is the unit of inventory.

    ANTI-REDUNDANCY RULE:
    - Stock is NOT stored here
    - Sizes and colors are NOT stored as text
    - Season is NOT duplicated from product
    """

    product = models.ForeignKey(
        'Product',
        on_delete=models.CASCADE,
        related_name='variants',
        verbose_name='Producto',
    )

    size = models.ForeignKey(
        'Size',
        on_delete=models.PROTECT,
        related_name='variants',
        verbose_name='Talla',
    )

    color = models.ForeignKey(
        'Color',
        on_delete=models.PROTECT,
        related_name='variants',
        verbose_name='Color',
    )

    # Auto-generated SKU
    sku = models.CharField('SKU', max_length=32, unique=True, editable=False)

    # Optional barcode for POS scanner
    barcode = models.CharField(
        'Código de barras',
        max_length=32,
        unique=True,
        null=True,
        blank=True,
    )

    # Price override (if this variant differs from base_price)
    price_override = models.DecimalField(
        'Precio específico',
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Dejar vacío para usar el precio base del producto',
    )

    is_active = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'product_variants'
        verbose_name = 'Variante de Producto'
        verbose_name_plural = 'Variantes de Producto'
        unique_together = [['product', 'size', 'color']]
        indexes = [
            models.Index(fields=['product', 'is_active']),
            models.Index(fields=['sku']),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.size.code} - {self.color.name}"

    @property
    def effective_price(self):
        """Return the actual price (override or base)."""
        return self.price_override if self.price_override is not None else self.product.base_price

    def save(self, *args, **kwargs):
        """Auto-generate SKU if not set."""
        if not self.sku:
            if not self.product_id or not self.size_id or not self.color_id:
                raise ValueError(
                    'product, size and color are required before saving a variant',
                )
            self.sku = (
                f"{self.product_id}-{self.size.code}-{self.color.slug}".upper()
            )
        super().save(*args, **kwargs)


# =============================================================================
# PRODUCT IMAGES & AR ASSETS
# =============================================================================

class ProductImage(TimeStampedModel):
    """Product image."""

    product = models.ForeignKey(
        'Product',
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name='Producto',
    )

    # Color-specific image (null = applies to all colors)
    color = models.ForeignKey(
        'Color',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='images',
        verbose_name='Color',
    )

    image = models.ImageField('Imagen', upload_to='products/')
    alt_text = models.CharField('Texto alternativo', max_length=200, blank=True)

    is_primary = models.BooleanField('Imagen principal', default=False)
    display_order = models.PositiveIntegerField('Orden', default=0)

    class Meta:
        db_table = 'product_images'
        verbose_name = 'Imagen de Producto'
        verbose_name_plural = 'Imágenes de Producto'
        ordering = ['product', '-is_primary', 'display_order']

    def __str__(self):
        color_info = f" - {self.color.name}" if self.color else ""
        return f"Imagen de {self.product.name}{color_info}"


class ARAsset(TimeStampedModel):
    """
    Augmented Reality asset for virtual try-on.

    Assets are per product+color, NOT per variant (size is applied as scale).
    """

    OVERLAY_2D = 'OVERLAY_2D'
    MODEL_3D = 'MODEL_3D'

    KIND_CHOICES = [
        (OVERLAY_2D, 'Overlay 2D'),
        (MODEL_3D, 'Modelo 3D'),
    ]

    product = models.ForeignKey(
        'Product',
        on_delete=models.CASCADE,
        related_name='ar_assets',
        verbose_name='Producto',
    )

    color = models.ForeignKey(
        'Color',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='ar_assets',
        verbose_name='Color',
    )

    kind = models.CharField('Tipo', max_length=20, choices=KIND_CHOICES)
    file = models.FileField('Archivo', upload_to='ar_assets/')

    # JSON configuration for AR engine
    anchor_config = models.JSONField(
        'Configuración de anclaje',
        default=dict,
        blank=True,
        help_text='Puntos de anclaje, escala, offsets para el motor AR',
    )

    is_active = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'ar_assets'
        verbose_name = 'Asset AR'
        verbose_name_plural = 'Assets AR'
        unique_together = [['product', 'color', 'kind']]

    def __str__(self):
        color_info = f" - {self.color.name}" if self.color else ""
        return f"AR {self.get_kind_display()} de {self.product.name}{color_info}"
