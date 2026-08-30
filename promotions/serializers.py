"""
Serializers for promotions app.
"""
from rest_framework import serializers

from promotions.models import Promotion


class PromotionSerializer(serializers.ModelSerializer):
    """Promotion / coupon CRUD."""

    class Meta:
        model = Promotion
        fields = [
            'id',
            'name',
            'code',
            'discount_type',
            'value',
            'starts_at',
            'ends_at',
            'min_order_amount',
            'max_uses',
            'used_count',
            'categories',
            'collections',
            'products',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'used_count', 'created_at', 'updated_at']


class PromotionValidateSerializer(serializers.Serializer):
    """Validate a coupon code at checkout."""

    code = serializers.CharField(max_length=50)
    order_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
