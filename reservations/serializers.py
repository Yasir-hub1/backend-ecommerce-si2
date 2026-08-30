"""
Serializers for reservations app.
"""
from rest_framework import serializers
from datetime import timedelta
from django.utils import timezone

from reservations.models import (
    Reservation,
    ReservationItem,
    ReservationStatus,
    ItemStatus,
)
from catalog.serializers import ProductVariantListSerializer


class ReservationItemSerializer(serializers.ModelSerializer):
    """Reservation item serializer."""
    variant = ProductVariantListSerializer(read_only=True)
    product_name = serializers.CharField(source='variant.product.name', read_only=True)
    item_status_display = serializers.CharField(source='get_item_status_display', read_only=True)

    class Meta:
        model = ReservationItem
        fields = [
            'id',
            'variant',
            'product_name',
            'quantity',
            'item_status',
            'item_status_display',
        ]
        read_only_fields = ['id', 'item_status']


class ReservationListSerializer(serializers.ModelSerializer):
    """Simplified reservation serializer for list views."""
    customer_name = serializers.CharField(source='customer.user.get_full_name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    items_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Reservation
        fields = [
            'id',
            'code',
            'customer_name',
            'branch_name',
            'scheduled_for',
            'expires_at',
            'status',
            'status_display',
            'items_count',
            'created_at',
        ]
        read_only_fields = ['id', 'code']


class ReservationDetailSerializer(serializers.ModelSerializer):
    """Detailed reservation serializer with all items."""
    items = ReservationItemSerializer(many=True, read_only=True)
    customer_email = serializers.CharField(source='customer.user.email', read_only=True)
    customer_phone = serializers.CharField(source='customer.user.phone', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    prepared_by_name = serializers.CharField(
        source='prepared_by.get_full_name',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = Reservation
        fields = [
            'id',
            'code',
            'customer',
            'customer_email',
            'customer_phone',
            'branch',
            'branch_name',
            'scheduled_for',
            'expires_at',
            'status',
            'status_display',
            'items',
            'notes',
            'prepared_by',
            'prepared_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'code',
            'customer',
            'status',
            'prepared_by',
            'created_at',
            'updated_at',
        ]


class CreateReservationSerializer(serializers.Serializer):
    """Create reservation serializer."""
    branch_id = serializers.IntegerField()
    scheduled_for = serializers.DateTimeField()
    items = serializers.ListField(
        child=serializers.DictField(),
        min_length=1
    )
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_branch_id(self, value):
        """Validate branch exists and is active."""
        from branches.models import Branch
        if not Branch.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("Sucursal no válida")
        return value

    def validate_scheduled_for(self, value):
        """Validate scheduled time is in the future."""
        if value <= timezone.now():
            raise serializers.ValidationError(
                "La fecha de reserva debe ser en el futuro"
            )

        # Don't allow reservations more than 30 days in advance
        max_advance = timezone.now() + timedelta(days=30)
        if value > max_advance:
            raise serializers.ValidationError(
                "No se pueden hacer reservas con más de 30 días de anticipación"
            )

        return value

    def validate_items(self, value):
        """Validate items structure and variants."""
        from catalog.models import ProductVariant

        if not value:
            raise serializers.ValidationError("Debe incluir al menos un artículo")

        for item in value:
            if 'variant_id' not in item or 'quantity' not in item:
                raise serializers.ValidationError(
                    "Cada artículo debe tener variant_id y quantity"
                )

            # Validate variant exists
            if not ProductVariant.objects.filter(
                id=item['variant_id'],
                is_active=True
            ).exists():
                raise serializers.ValidationError(
                    f"Variante {item['variant_id']} no válida"
                )

            # Validate quantity
            if item['quantity'] < 1:
                raise serializers.ValidationError(
                    "La cantidad debe ser al menos 1"
                )

        return value


class TransitionReservationSerializer(serializers.Serializer):
    """Transition reservation status."""
    new_status = serializers.ChoiceField(choices=ReservationStatus.CHOICES)


class CancelReservationSerializer(serializers.Serializer):
    """Cancel reservation serializer."""
    reason = serializers.CharField(required=False, allow_blank=True, default='')
