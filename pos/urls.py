"""URL configuration for POS app."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from pos.views import (
    POSBarcodeLookupView,
    POSCatalogSearchView,
    POSCustomerCreateView,
    POSCustomerSearchView,
    POSDailySummaryView,
    POSOrderViewSet,
    POSPaymentPreviewView,
    POSQuoteView,
    POSReservationLookupView,
    POSSaleView,
)

router = DefaultRouter()
router.register(r'sales', POSOrderViewSet, basename='pos-order')

urlpatterns = [
    path('search/', POSCatalogSearchView.as_view(), name='pos-search'),
    path('lookup/', POSBarcodeLookupView.as_view(), name='pos-lookup'),
    path('quote/', POSQuoteView.as_view(), name='pos-quote'),
    path('payments/preview/', POSPaymentPreviewView.as_view(), name='pos-payment-preview'),
    path('sales/checkout/', POSSaleView.as_view(), name='pos-sale'),
    path('customers/', POSCustomerSearchView.as_view(), name='pos-customers-search'),
    path('customers/create/', POSCustomerCreateView.as_view(), name='pos-customers-create'),
    path('reservations/lookup/', POSReservationLookupView.as_view(), name='pos-reservation-lookup'),
    path('daily-summary/', POSDailySummaryView.as_view(), name='pos-daily-summary'),
    path('', include(router.urls)),
]
