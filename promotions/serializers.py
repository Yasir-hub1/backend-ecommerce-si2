"""
Serializers for promotions app.
"""
from decimal import Decimal

from rest_framework import serializers

from promotions.models import DiscountType, Promotion


class PromotionSerializer(serializers.ModelSerializer):
    """Promotion / coupon CRUD.

    Frontend aliases:
    - discount_value ↔ value
    - uses_count ↔ used_count
    - PERCENTAGE ↔ PERCENT
    - description is accepted/ignored (not stored on the model yet)
    """

    discount_value = serializers.DecimalField(
        source='value',
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('0'),
    )
    uses_count = serializers.IntegerField(source='used_count', read_only=True)
    description = serializers.CharField(required=False, allow_blank=True, write_only=True, default='')
    discount_type = serializers.ChoiceField(
        choices=[
            ('PERCENT', 'Porcentaje'),
            ('PERCENTAGE', 'Porcentaje'),
            ('FIXED', 'Monto fijo'),
        ],
    )

    class Meta:
        model = Promotion
        fields = [
            'id',
            'name',
            'code',
            'description',
            'discount_type',
            'discount_value',
            'starts_at',
            'ends_at',
            'min_order_amount',
            'max_uses',
            'uses_count',
            'used_count',
            'categories',
            'collections',
            'products',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'uses_count',
            'used_count',
            'created_at',
            'updated_at',
        ]

    def validate_discount_type(self, value: str) -> str:
        if value == 'PERCENTAGE':
            return DiscountType.PERCENT
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data.get('discount_type') == DiscountType.PERCENT:
            data['discount_type'] = 'PERCENTAGE'
        data['description'] = ''
        return data

    def create(self, validated_data):
        validated_data.pop('description', None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop('description', None)
        return super().update(instance, validated_data)


class PromotionValidateSerializer(serializers.Serializer):
    """Input for POST /promotions/validate/ before checkout."""

    code = serializers.CharField(max_length=50)
    order_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0'),
    )
