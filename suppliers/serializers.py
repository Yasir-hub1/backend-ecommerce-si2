"""
Serializers for suppliers app.
"""
from rest_framework import serializers

from suppliers.models import (
    Supplier,
    PurchaseReceipt,
    PurchaseReceiptItem,
    PurchaseReceiptStatus,
    ProductSubmission,
    ProductSubmissionStatus,
)


class SupplierSerializer(serializers.ModelSerializer):
    """Supplier CRUD (RF06)."""

    class Meta:
        model = Supplier
        fields = [
            'id',
            'legal_name',
            'trade_name',
            'tax_id',
            'email',
            'phone',
            'address',
            'user',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PurchaseReceiptItemSerializer(serializers.ModelSerializer):
    """Line item in a purchase receipt."""

    variant_sku = serializers.CharField(source='variant.sku', read_only=True)
    line_total = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True,
    )

    class Meta:
        model = PurchaseReceiptItem
        fields = [
            'id',
            'variant',
            'variant_sku',
            'quantity',
            'unit_cost',
            'line_total',
        ]
        read_only_fields = ['id']


class PurchaseReceiptSerializer(serializers.ModelSerializer):
    """Purchase receipt with nested items."""

    items = PurchaseReceiptItemSerializer(many=True)
    supplier_name = serializers.CharField(
        source='supplier.trade_name', read_only=True,
    )
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = PurchaseReceipt
        fields = [
            'id',
            'code',
            'supplier',
            'supplier_name',
            'branch',
            'branch_code',
            'status',
            'status_display',
            'received_at',
            'received_by',
            'invoice_number',
            'notes',
            'items',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'code', 'status', 'received_at', 'received_by',
            'created_at', 'updated_at',
        ]

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        receipt = PurchaseReceipt.objects.create(**validated_data)
        for item_data in items_data:
            PurchaseReceiptItem.objects.create(receipt=receipt, **item_data)
        return receipt

    def update(self, instance, validated_data):
        if instance.status != PurchaseReceiptStatus.DRAFT:
            raise serializers.ValidationError(
                'Solo se pueden editar recepciones en estado DRAFT'
            )
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                PurchaseReceiptItem.objects.create(receipt=instance, **item_data)
        return instance


class PurchaseReceiptListSerializer(serializers.ModelSerializer):
    """Lightweight receipt for list views."""

    supplier_name = serializers.CharField(source='supplier.trade_name', read_only=True)
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    item_count = serializers.IntegerField(source='items.count', read_only=True)

    class Meta:
        model = PurchaseReceipt
        fields = [
            'id', 'code', 'supplier_name', 'branch_code',
            'status', 'received_at', 'item_count', 'created_at',
        ]


class CancelReceiptSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ProductSubmissionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    collection_name = serializers.CharField(source='collection.name', read_only=True)

    class Meta:
        model = ProductSubmission
        fields = [
            'id',
            'supplier',
            'name',
            'description',
            'collection',
            'collection_name',
            'gender',
            'base_price',
            'material',
            'status',
            'status_display',
            'review_notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'supplier',
            'status',
            'status_display',
            'review_notes',
            'created_at',
            'updated_at',
        ]
