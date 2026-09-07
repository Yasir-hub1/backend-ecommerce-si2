"""
Serializers for payments app.
"""
from rest_framework import serializers
from payments.models import Payment, PaymentMethod, PaymentProvider


class PaymentSerializer(serializers.ModelSerializer):
    """Payment serializer."""
    method_display = serializers.CharField(source='get_method_display', read_only=True)
    provider_display = serializers.CharField(source='get_provider_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Payment
        fields = [
            'id',
            'order',
            'method',
            'method_display',
            'provider',
            'provider_display',
            'status',
            'status_display',
            'amount',
            'currency',
            'stripe_payment_intent_id',
            'paid_at',
            'refunded_at',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'order',
            'status',
            'stripe_payment_intent_id',
            'paid_at',
            'refunded_at',
            'created_at',
        ]


class CreateCheckoutSessionSerializer(serializers.Serializer):
    """Create Stripe Checkout Session serializer."""
    order_id = serializers.IntegerField()

    def validate_order_id(self, value):
        """Validate order exists and is pending payment."""
        from orders.models import Order, OrderStatus

        try:
            order = Order.objects.get(id=value)
        except Order.DoesNotExist:
            raise serializers.ValidationError("Orden no encontrada")

        if order.status != OrderStatus.PENDING_PAYMENT:
            raise serializers.ValidationError(
                "La orden no está pendiente de pago"
            )

        return value


class ConfirmPaymentIntentSerializer(serializers.Serializer):
    """Confirm PaymentIntent after client-side PaymentSheet success."""

    order_id = serializers.IntegerField()

    def validate_order_id(self, value):
        from orders.models import Order

        if not Order.objects.filter(id=value).exists():
            raise serializers.ValidationError('Orden no encontrada')
        return value
