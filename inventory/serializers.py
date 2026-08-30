"""
Serializers for inventory app.
"""
from rest_framework import serializers

from inventory.models import BranchStock, InventoryMovement


class BranchStockSerializer(serializers.ModelSerializer):
    """Stock level per branch and variant."""

    variant_sku = serializers.CharField(source='variant.sku', read_only=True)
    product_name = serializers.CharField(source='variant.product.name', read_only=True)
    size_code = serializers.CharField(source='variant.size.code', read_only=True)
    color_name = serializers.CharField(source='variant.color.name', read_only=True)
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    available = serializers.IntegerField(read_only=True)

    class Meta:
        model = BranchStock
        fields = [
            'id',
            'branch',
            'branch_code',
            'branch_name',
            'variant',
            'variant_sku',
            'product_name',
            'size_code',
            'color_name',
            'on_hand',
            'reserved',
            'available',
            'min_threshold',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'on_hand', 'reserved', 'created_at', 'updated_at',
        ]


class InventoryMovementSerializer(serializers.ModelSerializer):
    """Read-only ledger entry."""

    variant_sku = serializers.CharField(source='variant.sku', read_only=True)
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    movement_type_display = serializers.CharField(
        source='get_movement_type_display', read_only=True,
    )
    created_by_email = serializers.CharField(
        source='created_by.email', read_only=True, default=None,
    )

    class Meta:
        model = InventoryMovement
        fields = [
            'id',
            'branch',
            'branch_code',
            'variant',
            'variant_sku',
            'movement_type',
            'movement_type_display',
            'quantity',
            'reference_type',
            'reference_id',
            'note',
            'created_by',
            'created_by_email',
            'created_at',
        ]
        read_only_fields = fields


class StockAdjustSerializer(serializers.Serializer):
    """Manual stock adjustment (in/out)."""

    branch_id = serializers.IntegerField()
    variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    direction = serializers.ChoiceField(choices=['in', 'out'])
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)


class StockTransferSerializer(serializers.Serializer):
    """Inter-branch stock transfer."""

    from_branch_id = serializers.IntegerField()
    to_branch_id = serializers.IntegerField()
    variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs['from_branch_id'] == attrs['to_branch_id']:
            raise serializers.ValidationError(
                'La sucursal origen y destino deben ser distintas'
            )
        return attrs


class BranchStockThresholdSerializer(serializers.ModelSerializer):
    """Update minimum stock threshold."""

    class Meta:
        model = BranchStock
        fields = ['min_threshold']
