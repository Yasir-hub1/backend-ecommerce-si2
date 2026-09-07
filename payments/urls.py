"""
URL configuration for payments app.
"""
from django.urls import path

from payments.views import (
    ConfirmPaymentIntentView,
    CreateCheckoutSessionView,
    CreatePaymentIntentView,
    PaymentsConfigView,
    StripeWebhookView,
    GetCheckoutSessionStatusView,
)

urlpatterns = [
    path('payments/config/', PaymentsConfigView.as_view(), name='payments-config'),
    path('payments/intent/', CreatePaymentIntentView.as_view(), name='payments-intent'),
    path(
        'payments/intent/confirm/',
        ConfirmPaymentIntentView.as_view(),
        name='payments-intent-confirm',
    ),
    path('checkout-session/', CreateCheckoutSessionView.as_view(), name='create-checkout-session'),
    path('webhook/stripe/', StripeWebhookView.as_view(), name='stripe-webhook'),
    path(
        'checkout-session/<str:session_id>/status/',
        GetCheckoutSessionStatusView.as_view(),
        name='checkout-session-status',
    ),
]
