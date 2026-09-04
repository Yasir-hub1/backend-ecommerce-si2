"""
Views for catalog app.
"""
import uuid

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated, AllowAny
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

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
from catalog.serializers import (
    CategorySerializer,
    BrandSerializer,
    SizeGroupSerializer,
    SizeSerializer,
    ColorSerializer,
    SeasonSerializer,
    CollectionSerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductVariantDetailSerializer,
    ProductVariantWriteSerializer,
    ProductImageSerializer,
    GenerateVariantsSerializer,
    ProductVariantListSerializer,
    ARAssetSerializer,
    PublicARAssetSerializer,
    ProductWithAvailabilitySerializer,
)
from core.mixins import PublicReadRBACWriteMixin, ReferenceCountQuerysetMixin
from core.permissions import HasAppPermission
from core.exceptions import BusinessError

CATALOG_WRITE = 'catalog.products.manage'
IMAGE_UPLOAD_PARSERS = [MultiPartParser, FormParser, JSONParser]
CATALOG_WRITE_ACTIONS = frozenset({
    'images',
    'image_detail',
    'variants_generate',
    'ar_assets',
})


class CategoryViewSet(ReferenceCountQuerysetMixin, PublicReadRBACWriteMixin, viewsets.ModelViewSet):
    """
    Category management.

    Public can list/retrieve, admin can modify.
    """
    queryset = Category.objects.filter(is_active=True).order_by('name')
    serializer_class = CategorySerializer
    write_permission = CATALOG_WRITE
    reference_count_fields = {
        'products_count': 'products',
        'children_count': 'children',
    }

    def get_queryset(self):
        """Admin sees all, others see only active."""
        qs = super().get_queryset().order_by('display_order', 'name')
        if self.request.user.is_authenticated and hasattr(self.request.user, 'role'):
            from accounts.models import Role
            if self.request.user.role == Role.ADMIN:
                return qs
        return qs.filter(is_active=True)


class BrandViewSet(ReferenceCountQuerysetMixin, PublicReadRBACWriteMixin, viewsets.ModelViewSet):
    """Brand management."""
    queryset = Brand.objects.all().order_by('name')
    serializer_class = BrandSerializer
    write_permission = CATALOG_WRITE
    parser_classes = IMAGE_UPLOAD_PARSERS
    reference_count_fields = {'products_count': 'products'}


class SizeGroupViewSet(PublicReadRBACWriteMixin, viewsets.ModelViewSet):
    """Size group management."""
    queryset = SizeGroup.objects.all().order_by('name')
    serializer_class = SizeGroupSerializer
    write_permission = CATALOG_WRITE


class SizeViewSet(ReferenceCountQuerysetMixin, PublicReadRBACWriteMixin, viewsets.ModelViewSet):
    """Size management."""
    queryset = Size.objects.select_related('group').all().order_by('group__name', 'display_order')
    serializer_class = SizeSerializer
    write_permission = CATALOG_WRITE
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['group']
    reference_count_fields = {'variants_count': 'variants'}


class ColorViewSet(ReferenceCountQuerysetMixin, PublicReadRBACWriteMixin, viewsets.ModelViewSet):
    """Color management."""
    queryset = Color.objects.all().order_by('name')
    serializer_class = ColorSerializer
    write_permission = CATALOG_WRITE
    reference_count_fields = {'variants_count': 'variants'}


class SeasonViewSet(ReferenceCountQuerysetMixin, PublicReadRBACWriteMixin, viewsets.ModelViewSet):
    """Season management (RF05, RF23)."""
    queryset = Season.objects.filter(is_active=True).order_by('-starts_on')
    serializer_class = SeasonSerializer
    write_permission = CATALOG_WRITE
    reference_count_fields = {'collections_count': 'collections'}

    def get_queryset(self):
        qs = super().get_queryset().order_by('-starts_on')
        if self.request.user.is_authenticated and hasattr(self.request.user, 'role'):
            from accounts.models import Role
            if self.request.user.role == Role.ADMIN:
                return qs
        return qs.filter(is_active=True)


class CollectionViewSet(ReferenceCountQuerysetMixin, PublicReadRBACWriteMixin, viewsets.ModelViewSet):
    """Collection management (RF23). Filter by season for tallas/colecciones por temporada."""
    queryset = Collection.objects.select_related('season').filter(is_active=True).order_by('-created_at')
    serializer_class = CollectionSerializer
    write_permission = CATALOG_WRITE
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['season', 'supplier']
    reference_count_fields = {'products_count': 'products'}

    def get_queryset(self):
        qs = super().get_queryset().select_related('season').order_by('-launch_date', '-created_at')
        if self.request.user.is_authenticated and hasattr(self.request.user, 'role'):
            from accounts.models import Role
            if self.request.user.role == Role.ADMIN:
                return qs
        return qs.filter(is_active=True)


class ProductViewSet(PublicReadRBACWriteMixin, viewsets.ModelViewSet):
    """
    Product catalog.

    Public can browse with filters and search.
    Admin can create/update/delete.

    Filters:
    - category, brand, collection, gender
    - min_price, max_price
    - branch (for availability filtering)

    Search: name, description
    Ordering: -created_at, price, name
    """
    queryset = Product.objects.select_related(
        'category', 'brand', 'collection__season'
    ).prefetch_related('images', 'variants').filter(is_active=True)
    write_permission = CATALOG_WRITE
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'category': ['exact'],
        'brand': ['exact'],
        'collection': ['exact'],
        'gender': ['exact'],
        'base_price': ['gte', 'lte'],
    }
    search_fields = ['name', 'description', 'material']
    ordering_fields = ['created_at', 'base_price', 'name']
    ordering = ['-created_at']

    IMAGE_WRITE_ACTIONS = CATALOG_WRITE_ACTIONS

    def get_permissions(self):
        if self.action in self.IMAGE_WRITE_ACTIONS:
            return [IsAuthenticated(), HasAppPermission()]
        return super().get_permissions()

    def get_serializer_class(self):
        """Use different serializers for list vs detail."""
        if self.action == 'list':
            # Check if branch_id is provided for availability
            if self.request.query_params.get('branch'):
                return ProductWithAvailabilitySerializer
            return ProductListSerializer
        return ProductDetailSerializer

    def get_serializer_context(self):
        """Add branch_id to context for availability serializer."""
        context = super().get_serializer_context()
        branch_id = self.request.query_params.get('branch')
        if branch_id:
            context['branch_id'] = int(branch_id)
        return context

    def get_queryset(self):
        """Admin sees all, others see only active."""
        qs = self.queryset

        if self.request.user.is_authenticated and hasattr(self.request.user, 'role'):
            from accounts.models import Role
            if self.request.user.role == Role.ADMIN:
                qs = Product.objects.select_related(
                    'category', 'brand', 'collection__season'
                ).prefetch_related('images', 'variants').all()

        # Filter by availability in branch if branch param provided
        branch_id = self.request.query_params.get('branch')
        if branch_id:
            # Only show products that have at least one variant with available stock
            from django.db.models import F, Exists, OuterRef
            from inventory.models import BranchStock

            available_stocks = BranchStock.objects.filter(
                variant=OuterRef('variants__id'),
                branch_id=branch_id,
                on_hand__gt=F('reserved')
            )

            qs = qs.filter(
                Exists(available_stocks)
            ).distinct()

        size_id = self.request.query_params.get('size')
        color_id = self.request.query_params.get('color')
        supplier_id = self.request.query_params.get('supplier')

        if size_id:
            qs = qs.filter(variants__size_id=size_id, variants__is_active=True).distinct()
        if color_id:
            qs = qs.filter(variants__color_id=color_id, variants__is_active=True).distinct()
        if supplier_id:
            qs = qs.filter(collection__supplier_id=supplier_id)

        return qs

    def get_object(self):
        lookup = self.kwargs.get(self.lookup_field)
        try:
            uuid.UUID(str(lookup))
        except (ValueError, TypeError, AttributeError):
            return super().get_object()
        qs = self.filter_queryset(self.get_queryset())
        return get_object_or_404(qs, public_id=lookup)

    def _ready_overlay(self, product, color_id=None):
        qs = product.ar_assets.filter(
            is_active=True,
            status=ARAsset.READY,
            kind=ARAsset.OVERLAY_2D,
        ).select_related('color')
        if color_id:
            qs = qs.filter(color_id=color_id)
        return qs.order_by('-updated_at').first()

    @action(detail=True, methods=['get'])
    def availability(self, request, pk=None):
        """
        Get product availability across all branches or specific branch.

        Query params:
        - branch: optional branch ID to filter
        """
        from branches.models import Branch
        from inventory.services import get_stock_levels, get_total_stock

        product = self.get_object()
        branch_id = request.query_params.get('branch')

        branch = None
        if branch_id is not None:
            try:
                branch = Branch.objects.get(pk=branch_id, is_active=True)
            except (Branch.DoesNotExist, ValueError, TypeError):
                return Response(
                    {'detail': 'Sucursal no encontrada.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        variants = product.variants.filter(is_active=True).select_related('size', 'color')
        availability_data = []

        for variant in variants:
            variant_data = {
                'variant_id': variant.id,
                'sku': variant.sku,
                'size': variant.size.code,
                'color': variant.color.name,
                'price': variant.effective_price,
                'branches': [],
            }

            if branch is not None:
                levels = get_stock_levels(branch=branch, variant_id=variant.id)
                variant_data['branches'].append({
                    'branch_id': branch.id,
                    'branch_code': branch.code,
                    'branch_name': branch.name,
                    **levels,
                })
            else:
                total = get_total_stock(variant_id=variant.id)
                variant_data['branches'] = total['branches']

            variant_data['total_available'] = sum(
                b['available'] for b in variant_data['branches']
            )
            availability_data.append(variant_data)

        return Response({
            'product_id': product.id,
            'product_name': product.name,
            'variants': availability_data,
        })

    @action(
        detail=True,
        methods=['get', 'post'],
        url_path='images',
        parser_classes=IMAGE_UPLOAD_PARSERS,
    )
    def images(self, request, pk=None):
        """List or upload images for a product (multipart/form-data)."""
        product = self.get_object()

        if request.method == 'GET':
            queryset = product.images.select_related('color').order_by('-is_primary', 'display_order')
            serializer = ProductImageSerializer(
                queryset,
                many=True,
                context={'request': request},
            )
            return Response(serializer.data)

        payload = request.data.copy()
        payload['product'] = product.id
        serializer = ProductImageSerializer(
            data=payload,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(product=product)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=['get', 'patch', 'put', 'delete'],
        url_path=r'images/(?P<image_id>[^/.]+)',
        parser_classes=IMAGE_UPLOAD_PARSERS,
    )
    def image_detail(self, request, pk=None, image_id=None):
        """Retrieve, update or delete a single product image."""
        product = self.get_object()

        try:
            image = product.images.select_related('color').get(pk=image_id)
        except ProductImage.DoesNotExist:
            return Response(
                {'detail': 'Imagen no encontrada.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.method == 'GET':
            serializer = ProductImageSerializer(image, context={'request': request})
            return Response(serializer.data)

        if request.method == 'DELETE':
            image.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        partial = request.method == 'PATCH'
        serializer = ProductImageSerializer(
            image,
            data=request.data,
            partial=partial,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(product=product)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=['get', 'post'],
        url_path='ar-assets',
        parser_classes=IMAGE_UPLOAD_PARSERS,
    )
    def ar_assets(self, request, pk=None):
        """List overlay assets, or upload a garment image for processing."""
        product = self.get_object()

        if request.method == 'GET':
            queryset = product.ar_assets.select_related('color').order_by('color_id', '-updated_at')
            if not (
                request.user.is_authenticated
                and getattr(request.user, 'role', None) == 'ADMIN'
            ):
                queryset = queryset.filter(
                    is_active=True,
                    status=ARAsset.READY,
                    kind=ARAsset.OVERLAY_2D,
                )
            serializer = ARAssetSerializer(
                queryset,
                many=True,
                context={'request': request},
            )
            return Response(serializer.data)

        payload = request.data.copy()
        payload['product'] = product.id
        payload.setdefault('kind', ARAsset.OVERLAY_2D)
        serializer = ARAssetSerializer(data=payload, context={'request': request})
        serializer.is_valid(raise_exception=True)
        asset = serializer.save(product=product, status=ARAsset.PROCESSING)

        from catalog.tasks import enqueue_ar_asset_build

        task_id = enqueue_ar_asset_build(asset.id)
        asset.refresh_from_db()
        body = ARAssetSerializer(asset, context={'request': request}).data
        body['task_id'] = task_id
        return Response(body, status=status.HTTP_202_ACCEPTED)

    @action(
        detail=True,
        methods=['get'],
        url_path='ar-asset',
        permission_classes=[AllowAny],
    )
    def public_ar_asset(self, request, pk=None):
        """Public overlay for the mobile try-on: ?color="""
        product = self.get_object()
        color = request.query_params.get('color')
        asset = self._ready_overlay(product, color_id=color or None)
        if asset is None:
            return Response(
                {'detail': 'No hay asset AR listo para este color.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            PublicARAssetSerializer(asset, context={'request': request}).data,
        )

    @action(detail=True, methods=['post'], url_path='variants/generate')
    def variants_generate(self, request, pk=None):
        """Bulk-create variants as size × color combinations."""
        product = self.get_object()
        serializer = GenerateVariantsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from catalog.services.variants import generate_product_variants

        try:
            result = generate_product_variants(
                product_id=product.id,
                size_ids=serializer.validated_data['size_ids'],
                color_ids=serializer.validated_data['color_ids'],
                skip_existing=serializer.validated_data['skip_existing'],
            )
        except BusinessError as err:
            return Response(
                {'code': err.code, 'message': err.message, 'details': err.details},
                status=err.status_code,
            )

        variants_data = ProductVariantListSerializer(
            result['variants'],
            many=True,
            context={'request': request},
        ).data

        return Response(
            {
                'created_count': result['created_count'],
                'skipped_count': result['skipped_count'],
                'variants': variants_data,
            },
            status=status.HTTP_201_CREATED,
        )


class ProductVariantViewSet(PublicReadRBACWriteMixin, viewsets.ModelViewSet):
    """
    Product variant (SKU) management — product × size × color (RF04, RF05).
    """
    queryset = ProductVariant.objects.select_related(
        'product', 'size', 'color'
    ).filter(is_active=True)
    serializer_class = ProductVariantDetailSerializer
    write_permission = CATALOG_WRITE
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product', 'size', 'color', 'barcode', 'sku']

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return ProductVariantWriteSerializer
        return ProductVariantDetailSerializer

    def get_queryset(self):
        if self.request.user.is_authenticated and hasattr(self.request.user, 'role'):
            from accounts.models import Role
            if self.request.user.role == Role.ADMIN:
                return ProductVariant.objects.select_related('product', 'size', 'color').all()
        return ProductVariant.objects.select_related('product', 'size', 'color').filter(is_active=True)

    @action(detail=False, methods=['get'], url_path='lookup')
    def lookup(self, request):
        """Resolve active variant by barcode (or SKU fallback for POS)."""
        barcode = request.query_params.get('barcode', '').strip()
        if not barcode:
            return Response(
                {'detail': 'Parámetro barcode requerido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = self.get_queryset().select_related('product', 'size', 'color')
        variant = qs.filter(barcode=barcode).first()
        if variant is None:
            variant = qs.filter(sku=barcode).first()
        if variant is None:
            return Response(
                {'detail': 'Variante no encontrada.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = ProductVariantDetailSerializer(variant, context={'request': request}).data
        data['product_id'] = variant.product_id
        return Response(data)


class ProductImageViewSet(PublicReadRBACWriteMixin, viewsets.ModelViewSet):
    """Product image upload and management (global list/create)."""

    queryset = ProductImage.objects.select_related('product', 'color').order_by(
        'product', '-is_primary', 'display_order',
    )
    serializer_class = ProductImageSerializer
    write_permission = CATALOG_WRITE
    parser_classes = IMAGE_UPLOAD_PARSERS
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product', 'color', 'is_primary']


class ARAssetViewSet(PublicReadRBACWriteMixin, viewsets.ModelViewSet):
    """
    AR Asset management.

    Public can retrieve READY overlays for virtual try-on.
    Admin can create/update/delete and calibrate anchor_config.
    """
    queryset = ARAsset.objects.select_related('product', 'color')
    serializer_class = ARAssetSerializer
    write_permission = CATALOG_WRITE
    parser_classes = IMAGE_UPLOAD_PARSERS
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product', 'color', 'kind', 'status']

    def get_queryset(self):
        qs = self.queryset
        user = self.request.user
        if user.is_authenticated and getattr(user, 'role', None) == 'ADMIN':
            return qs
        return qs.filter(is_active=True, status=ARAsset.READY, kind=ARAsset.OVERLAY_2D)

    def perform_create(self, serializer):
        asset = serializer.save(status=ARAsset.PROCESSING)
        from catalog.tasks import enqueue_ar_asset_build

        enqueue_ar_asset_build(asset.id)
