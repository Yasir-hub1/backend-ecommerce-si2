"""
Serializers for catalog app.
"""
from rest_framework import serializers
from catalog.models import (
    Category,
    Brand,
    SizeGroup,
    Size,
    Color,
    Season,
    Collection,
    Product,
    ProductVariant,
    ProductImage,
    ARAsset,
)
from catalog.services.product_images import ensure_single_primary_image


def media_absolute_url(field, request) -> str | None:
    if not field:
        return None
    path = field.url
    if not path.startswith('/'):
        path = f'/{path}'
    if request:
        return request.build_absolute_uri(path)
    return path


class CategorySerializer(serializers.ModelSerializer):
    """Category serializer."""

    products_count = serializers.IntegerField(read_only=True, required=False)
    children_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'parent', 'size_group',
            'display_order', 'is_active', 'products_count', 'children_count',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class BrandSerializer(serializers.ModelSerializer):
    """Brand serializer with optional logo file upload."""

    logo_url = serializers.SerializerMethodField()
    remove_logo = serializers.BooleanField(write_only=True, required=False, default=False)
    products_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Brand
        fields = [
            'id',
            'name',
            'slug',
            'logo',
            'logo_url',
            'remove_logo',
            'products_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'logo_url', 'created_at', 'updated_at']
        extra_kwargs = {
            'logo': {'required': False, 'allow_null': True},
            'slug': {'required': False, 'allow_blank': True},
        }

    def get_logo_url(self, obj: Brand) -> str | None:
        return media_absolute_url(obj.logo, self.context.get('request'))

    def create(self, validated_data):
        validated_data.pop('remove_logo', None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        remove_logo = validated_data.pop('remove_logo', False)
        if remove_logo and instance.logo:
            instance.logo.delete(save=False)
            validated_data['logo'] = None
        return super().update(instance, validated_data)


class SizeGroupSerializer(serializers.ModelSerializer):
    """Size group serializer."""

    class Meta:
        model = SizeGroup
        fields = ['id', 'name', 'description']
        read_only_fields = ['id']


class SizeSerializer(serializers.ModelSerializer):
    """Size serializer."""
    group_name = serializers.CharField(source='group.name', read_only=True)
    variants_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Size
        fields = ['id', 'group', 'group_name', 'code', 'display_order', 'variants_count']
        read_only_fields = ['id']


class ColorSerializer(serializers.ModelSerializer):
    """Color serializer."""

    variants_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Color
        fields = ['id', 'name', 'slug', 'hex_code', 'variants_count']
        read_only_fields = ['id']


class SeasonSerializer(serializers.ModelSerializer):
    """Season serializer."""

    collections_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Season
        fields = [
            'id', 'name', 'code', 'kind', 'starts_on', 'ends_on', 'is_active',
            'collections_count', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class CollectionSerializer(serializers.ModelSerializer):
    """Collection serializer."""
    season_name = serializers.CharField(source='season.name', read_only=True)
    products_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Collection
        fields = [
            'id',
            'season',
            'season_name',
            'name',
            'slug',
            'supplier',
            'launch_date',
            'is_active',
            'products_count',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class ProductImageSerializer(serializers.ModelSerializer):
    """Product image serializer with absolute URL for admin/catalog UIs."""

    image_url = serializers.SerializerMethodField()
    color_name = serializers.CharField(source='color.name', read_only=True, allow_null=True)

    class Meta:
        model = ProductImage
        fields = [
            'id',
            'product',
            'image',
            'image_url',
            'alt_text',
            'color',
            'color_name',
            'is_primary',
            'display_order',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_image_url(self, obj: ProductImage) -> str | None:
        return media_absolute_url(obj.image, self.context.get('request'))

    def create(self, validated_data):
        image = super().create(validated_data)
        if image.is_primary:
            ensure_single_primary_image(product_id=image.product_id, primary_image_id=image.id)
        from catalog.services.ar_sync import sync_ar_from_product_image

        sync_ar_from_product_image(image)
        return image

    def update(self, instance, validated_data):
        new_file = validated_data.pop('image', None)
        if new_file is not None:
            from catalog.services.product_images import replace_product_image_file

            replace_product_image_file(instance=instance, new_file=new_file)
        image = super().update(instance, validated_data)
        if image.is_primary:
            ensure_single_primary_image(product_id=image.product_id, primary_image_id=image.id)
        if new_file is not None:
            from catalog.services.ar_sync import sync_ar_from_product_image

            sync_ar_from_product_image(image)
        return image


class ProductVariantListSerializer(serializers.ModelSerializer):
    """Simplified variant serializer for product listings."""
    size_name = serializers.CharField(source='size.code', read_only=True)
    color_name = serializers.CharField(source='color.name', read_only=True)
    color_hex = serializers.CharField(source='color.hex_code', read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            'id',
            'sku',
            'size',
            'size_name',
            'color',
            'color_name',
            'color_hex',
            'price_override',
            'effective_price',
            'is_active',
        ]
        read_only_fields = ['id', 'sku', 'effective_price']


class ProductVariantWriteSerializer(serializers.ModelSerializer):
    """Create/update variant using FK ids (product, size, color)."""

    class Meta:
        model = ProductVariant
        fields = [
            'id',
            'product',
            'size',
            'color',
            'price_override',
            'barcode',
            'is_active',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        product = attrs.get('product') or getattr(self.instance, 'product', None)
        size = attrs.get('size') or getattr(self.instance, 'size', None)
        color = attrs.get('color') or getattr(self.instance, 'color', None)

        if product and size and color:
            qs = ProductVariant.objects.filter(product=product, size=size, color=color)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    'Ya existe una variante con esta combinación producto/talla/color.',
                )
        return attrs

    def to_representation(self, instance):
        return ProductVariantDetailSerializer(instance, context=self.context).data


class ProductVariantDetailSerializer(serializers.ModelSerializer):
    """Detailed variant serializer with stock info."""
    size = SizeSerializer(read_only=True)
    color = ColorSerializer(read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            'id',
            'sku',
            'size',
            'color',
            'price_override',
            'effective_price',
            'barcode',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'sku', 'effective_price', 'created_at', 'updated_at']


class ProductListSerializer(serializers.ModelSerializer):
    """Simplified product serializer for list views."""
    category_name = serializers.CharField(source='category.name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    collection_name = serializers.CharField(source='collection.name', read_only=True)
    primary_image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id',
            'public_id',
            'name',
            'category_name',
            'brand_name',
            'collection_name',
            'base_price',
            'primary_image',
            'is_active',
        ]
        read_only_fields = ['id', 'public_id']

    def get_primary_image(self, obj):
        """Get primary image URL."""
        primary = obj.images.filter(is_primary=True).first()
        if not primary:
            return None
        return media_absolute_url(primary.image, self.context.get('request'))


class ProductDetailSerializer(serializers.ModelSerializer):
    """Detailed product serializer with all related data."""
    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    collection = CollectionSerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantListSerializer(many=True, read_only=True)

    # Write-only fields for creation
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source='category',
        write_only=True
    )
    brand_id = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(),
        source='brand',
        write_only=True
    )
    collection_id = serializers.PrimaryKeyRelatedField(
        queryset=Collection.objects.all(),
        source='collection',
        write_only=True
    )

    class Meta:
        model = Product
        fields = [
            'id',
            'public_id',
            'name',
            'description',
            'category',
            'category_id',
            'brand',
            'brand_id',
            'collection',
            'collection_id',
            'base_price',
            'gender',
            'material',
            'care_instructions',
            'is_active',
            'images',
            'variants',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'public_id', 'created_at', 'updated_at']


class GenerateVariantsSerializer(serializers.Serializer):
    size_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)
    color_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)
    skip_existing = serializers.BooleanField(default=True)


class ARAssetSerializer(serializers.ModelSerializer):
    """AR asset serializer (admin write + public read)."""

    file_url = serializers.SerializerMethodField()
    source_image_url = serializers.SerializerMethodField()
    error_message = serializers.CharField(source='process_error', read_only=True)

    class Meta:
        model = ARAsset
        fields = [
            'id',
            'product',
            'color',
            'kind',
            'status',
            'source_image',
            'source_image_url',
            'file',
            'file_url',
            'width',
            'height',
            'anchor_config',
            'process_error',
            'error_message',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'status',
            'file',
            'file_url',
            'source_image_url',
            'width',
            'height',
            'process_error',
            'error_message',
            'created_at',
            'updated_at',
        ]
        extra_kwargs = {
            'source_image': {'required': False},
            'kind': {'default': ARAsset.OVERLAY_2D},
        }

    def get_file_url(self, obj: ARAsset) -> str | None:
        return media_absolute_url(obj.file, self.context.get('request'))

    def get_source_image_url(self, obj: ARAsset) -> str | None:
        return media_absolute_url(obj.source_image, self.context.get('request'))

    def validate_source_image(self, value):
        from catalog.services.ar_assets import validate_ar_upload

        return validate_ar_upload(value)

    def validate_anchor_config(self, value):
        from core.ar import validate_anchor_config

        if not value:
            return value
        try:
            return validate_anchor_config(value)
        except ValueError as err:
            raise serializers.ValidationError(str(err)) from err

    def update(self, instance, validated_data):
        new_source = validated_data.get('source_image')
        if new_source is not None and instance.source_image:
            from catalog.services.media_cleanup import delete_field_file

            delete_field_file(instance.source_image)

        if 'anchor_config' in validated_data and validated_data['anchor_config']:
            config = dict(validated_data['anchor_config'])
            config['auto_calibrated'] = False
            validated_data['anchor_config'] = config

        asset = super().update(instance, validated_data)

        if new_source is not None:
            asset.status = ARAsset.PENDING
            asset.process_error = ''
            asset.save(update_fields=['status', 'process_error', 'updated_at'])
            from catalog.tasks import enqueue_ar_asset_build

            enqueue_ar_asset_build(asset.id)
        return asset


class PublicARAssetSerializer(serializers.ModelSerializer):
    """Contract consumed by the mobile try-on screen."""

    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ARAsset
        fields = [
            'id',
            'kind',
            'status',
            'file_url',
            'width',
            'height',
            'anchor_config',
            'updated_at',
        ]

    def get_file_url(self, obj: ARAsset) -> str | None:
        return media_absolute_url(obj.file, self.context.get('request'))


class ProductWithAvailabilitySerializer(ProductListSerializer):
    """Product serializer with availability info for a specific branch."""
    total_available = serializers.SerializerMethodField()
    variants_with_stock = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            'total_available',
            'variants_with_stock',
        ]

    def get_total_available(self, obj):
        """Get total available units across all variants for current branch."""
        branch_id = self.context.get('branch_id')
        if not branch_id:
            return None

        from django.db.models import F, Sum, Q

        total = obj.variants.filter(
            is_active=True,
            branch_stocks__branch_id=branch_id
        ).aggregate(
            available=Sum(
                F('branch_stocks__on_hand') - F('branch_stocks__reserved'),
                filter=Q(branch_stocks__branch_id=branch_id)
            )
        )['available']

        return total or 0

    def get_variants_with_stock(self, obj):
        """Get variants that have stock in current branch."""
        branch_id = self.context.get('branch_id')
        if not branch_id:
            return []

        from django.db.models import F

        variants = obj.variants.filter(
            is_active=True,
            branch_stocks__branch_id=branch_id
        ).annotate(
            available=F('branch_stocks__on_hand') - F('branch_stocks__reserved')
        ).filter(
            available__gt=0
        ).select_related('size', 'color')

        return ProductVariantListSerializer(variants, many=True).data
