"""
Views for payments app.
"""
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
from django.http import HttpResponse

from payments.serializers import CreateCheckoutSessionSerializer
from payments.services import (
    create_stripe_checkout_session,
    create_stripe_payment_intent,
    get_stripe_checkout_session_status,
    handle_stripe_webhook,
)
from core.exceptions import BusinessError


class PaymentsConfigView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'publishable_key': settings.STRIPE_PUBLISHABLE_KEY})


class CreatePaymentIntentView(generics.CreateAPIView):
    serializer_class = CreateCheckoutSessionSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_id = serializer.validated_data['order_id']

        from orders.models import Order
        from accounts.models import Role

        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({'detail': 'Orden no encontrada'}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role != Role.ADMIN:
            if not order.customer or order.customer.user_id != request.user.id:
                return Response({'detail': 'No autorizado'}, status=status.HTTP_403_FORBIDDEN)

        try:
            intent_data = create_stripe_payment_intent(order_id=order_id)
            return Response({'message': 'PaymentIntent creado', **intent_data}, status=status.HTTP_201_CREATED)
        except BusinessError as e:
            return Response(
                {'code': e.code, 'message': e.message, 'details': e.details},
                status=e.status_code,
            )


class CreateCheckoutSessionView(generics.CreateAPIView):
    """
    Create Stripe Checkout Session (ui_mode=elements) for an order.

    Authenticated users only.
    """
    serializer_class = CreateCheckoutSessionSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order_id = serializer.validated_data['order_id']

        from orders.models import Order
        from accounts.models import Role

        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response(
                {'detail': 'Orden no encontrada'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.user.role != Role.ADMIN:
            if not order.customer or order.customer.user_id != request.user.id:
                return Response(
                    {'detail': 'No autorizado'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        try:
            session_data = create_stripe_checkout_session(order_id=order_id)

            return Response(
                {
                    'message': 'Checkout session creada',
                    'checkout_session': session_data,
                },
                status=status.HTTP_201_CREATED,
            )

        except BusinessError as e:
            return Response(
                {'code': e.code, 'message': e.message, 'details': e.details},
                status=e.status_code,
            )


@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(APIView):
    """
    Stripe webhook endpoint.

    CRITICAL:
    - Must be csrf_exempt
    - Signature verification in service layer
    - Idempotent processing (event_id checked)
    """
    permission_classes = [AllowAny]

    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

        if not sig_header:
            return HttpResponse('Missing signature', status=400)

        try:
            result = handle_stripe_webhook(
                payload=payload,
                signature=sig_header,
            )

            return Response(result, status=status.HTTP_200_OK)

        except BusinessError as e:
            if e.code in ['INVALID_SIGNATURE', 'INVALID_PAYLOAD']:
                return HttpResponse(e.message, status=400)

            return HttpResponse(
                f'Webhook error: {e.message}',
                status=500,
            )

        except Exception as e:
            return HttpResponse(
                f'Internal error: {str(e)}',
                status=500,
            )


class GetCheckoutSessionStatusView(APIView):
    """
    Get Checkout Session status from Stripe.

    Used by frontend after redirect from payment confirmation.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        try:
            session_data = get_stripe_checkout_session_status(session_id=session_id)
            return Response(session_data)

        except BusinessError as e:
            return Response(
                {'code': e.code, 'message': e.message, 'details': e.details},
                status=e.status_code,
            )
