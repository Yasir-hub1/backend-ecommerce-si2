"""Serializers for POS API."""
from decimal import Decimal

from rest_framework import serializers

from payments.models import Payment, PaymentMethod


class POSLineItemSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class POSQuoteSerializer(serializers.Serializer):
    items = POSLineItemSerializer(many=True, min_length=1)


class POSPaymentInputSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=[code for code, _ in PaymentMethod.CHOICES])
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.01'),
    )
    received_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
    )


class POSPaymentPreviewSerializer(serializers.Serializer):
    items = POSLineItemSerializer(many=True, min_length=1)
    payments = POSPaymentInputSerializer(many=True, min_length=1)


class POSSaleSerializer(serializers.Serializer):
    """Create a POS sale (paid order with stock deduction)."""
    items = POSLineItemSerializer(many=True, min_length=1)
    payments = POSPaymentInputSerializer(many=True, min_length=1)
    customer_id = serializers.IntegerField(required=False, allow_null=True)
    reservation_id = serializers.IntegerField(required=False, allow_null=True)
    branch_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs):
        customer_id = attrs.get('customer_id')
        if customer_id:
            from accounts.models import CustomerProfile

            if not CustomerProfile.objects.filter(user_id=customer_id).exists():
                raise serializers.ValidationError({'customer_id': 'Cliente no encontrado'})

        reservation_id = attrs.get('reservation_id')
        if reservation_id:
            from reservations.models import Reservation

            if not Reservation.objects.filter(id=reservation_id).exists():
                raise serializers.ValidationError({'reservation_id': 'Reserva no encontrada'})

        return attrs


class POSPaymentSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(source='get_method_display', read_only=True)

    class Meta:
        model = Payment
        fields = [
            'id',
            'method',
            'method_display',
            'amount',
            'received_amount',
            'change_amount',
            'paid_at',
        ]


class POSOrderItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    variant_id = serializers.IntegerField(source='variant.id')
    product_name = serializers.CharField()
    sku = serializers.CharField(source='variant.sku')
    quantity = serializers.IntegerField()
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2)


class POSOrderSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    status = serializers.CharField()
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2)
    tax_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    grand_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    paid_at = serializers.DateTimeField()
    reservation_id = serializers.IntegerField(source='reservation_id', allow_null=True)
    items = POSOrderItemSerializer(many=True)
    payments = POSPaymentSerializer(many=True)
