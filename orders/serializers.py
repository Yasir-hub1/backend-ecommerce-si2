"""
Serializers for orders app.
"""
from typing import Optional
from rest_framework import serializers
from decimal import Decimal

from catalog.models import ProductVariant
from catalog.serializers import ProductVariantListSerializer
from inventory.services import get_stock_levels
from orders.models import Cart, CartItem, Order, OrderItem, OrderStatus, OrderChannel


class CartItemSerializer(serializers.ModelSerializer):
    """Cart item serializer with optional per-branch stock fields."""
    variant = ProductVariantListSerializer(read_only=True)
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.filter(is_active=True),
        source='variant',
        write_only=True,
    )
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    product_name = serializers.CharField(source='variant.product.name', read_only=True)
    available_qty = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()
    stock_status = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            'id',
            'variant',
            'variant_id',
            'quantity',
            'line_total',
            'product_name',
            'available_qty',
            'in_stock',
            'stock_status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'line_total',
            'product_name',
            'available_qty',
            'in_stock',
            'stock_status',
            'created_at',
            'updated_at',
        ]

    def validate_quantity(self, value):
        """Validate quantity is positive."""
        if value < 1:
            raise serializers.ValidationError("La cantidad debe ser al menos 1")
        return value

    def _available_for_item(self, obj) -> Optional[int]:
        """Return available units for the cart line's branch context, or None if unknown."""
        stock_by_variant = self.context.get('stock_by_variant')
        if stock_by_variant is not None:
            levels = stock_by_variant.get(obj.variant_id)
            if levels is None:
                return 0
            return int(levels['available'])

        branch = self.context.get('branch')
        if branch is None:
            return None
        return int(get_stock_levels(branch=branch, variant_id=obj.variant_id)['available'])

    def get_available_qty(self, obj):
        return self._available_for_item(obj)

    def get_in_stock(self, obj):
        available = self._available_for_item(obj)
        if available is None:
            return None
        return available >= obj.quantity

    def get_stock_status(self, obj):
        """
        OK — enough stock for cart quantity
        LOW — some stock but less than requested
        OUT — zero available
        UNKNOWN — no branch selected yet
        """
        available = self._available_for_item(obj)
        if available is None:
            return 'UNKNOWN'
        if available <= 0:
            return 'OUT'
        if available < obj.quantity:
            return 'LOW'
        return 'OK'


class CartSerializer(serializers.ModelSerializer):
    """Cart serializer with items and aggregate stock flags."""
    items = CartItemSerializer(many=True, read_only=True)
    total_items = serializers.IntegerField(read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    branch_id = serializers.SerializerMethodField()
    all_in_stock = serializers.SerializerMethodField()
    has_stock_issues = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            'id',
            'customer',
            'items',
            'total_items',
            'subtotal',
            'branch_id',
            'all_in_stock',
            'has_stock_issues',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'customer',
            'branch_id',
            'all_in_stock',
            'has_stock_issues',
            'created_at',
            'updated_at',
        ]

    def get_branch_id(self, obj):
        branch = self.context.get('branch')
        return branch.id if branch is not None else None

    def get_all_in_stock(self, obj):
        branch = self.context.get('branch')
        if branch is None:
            return None
        item_serializer = CartItemSerializer(context=self.context)
        return all(
            item_serializer.get_in_stock(item) is True
            for item in obj.items.all()
        )

    def get_has_stock_issues(self, obj):
        all_ok = self.get_all_in_stock(obj)
        if all_ok is None:
            return None
        return not all_ok


class OrderItemSerializer(serializers.ModelSerializer):
    """Order item serializer."""
    variant = ProductVariantListSerializer(read_only=True)
    product_name = serializers.CharField(source='variant.product.name', read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            'id',
            'variant',
            'product_name',
            'quantity',
            'unit_price',
            'discount_amount',
            'line_total',
        ]
        read_only_fields = ['id', 'line_total']


class OrderListSerializer(serializers.ModelSerializer):
    """Simplified order serializer for list views."""
    customer_name = serializers.CharField(source='customer.user.get_full_name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    channel_display = serializers.CharField(source='get_channel_display', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id',
            'code',
            'customer_name',
            'branch_name',
            'channel',
            'channel_display',
            'status',
            'status_display',
            'grand_total',
            'currency',
            'created_at',
            'paid_at',
        ]
        read_only_fields = ['id', 'code']


class OrderDetailSerializer(serializers.ModelSerializer):
    """Detailed order serializer with all items and payments."""
    items = OrderItemSerializer(many=True, read_only=True)
    customer_email = serializers.CharField(source='customer.user.email', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    channel_display = serializers.CharField(source='get_channel_display', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id',
            'code',
            'customer',
            'customer_email',
            'branch',
            'branch_name',
            'channel',
            'channel_display',
            'reservation',
            'status',
            'status_display',
            'items',
            'subtotal',
            'discount_total',
            'tax_total',
            'grand_total',
            'currency',
            'created_at',
            'updated_at',
            'paid_at',
        ]
        read_only_fields = [
            'id',
            'code',
            'customer',
            'status',
            'subtotal',
            'discount_total',
            'tax_total',
            'grand_total',
            'created_at',
            'updated_at',
            'paid_at',
        ]


class CheckoutSerializer(serializers.Serializer):
    """Checkout serializer."""
    branch_id = serializers.IntegerField()
    channel = serializers.ChoiceField(choices=OrderChannel.CHOICES, default=OrderChannel.WEB)
    promotion_code = serializers.CharField(required=False, allow_blank=True)

    def validate_branch_id(self, value):
        """Validate branch exists."""
        from branches.models import Branch
        if not Branch.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("Sucursal no válida")
        return value


class AddToCartSerializer(serializers.Serializer):
    """Add item to cart serializer."""
    variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)

    def validate_variant_id(self, value):
        """Validate variant exists and is active."""
        from catalog.models import ProductVariant
        if not ProductVariant.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("Variante no válida")
        return value


class UpdateCartItemSerializer(serializers.Serializer):
    """Update cart item quantity."""
    quantity = serializers.IntegerField(min_value=1)
