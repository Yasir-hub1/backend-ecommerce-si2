"""
URL configuration for suppliers app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from suppliers.views import SupplierViewSet, PurchaseReceiptViewSet, ProductSubmissionViewSet

router = DefaultRouter()
router.register(r'suppliers', SupplierViewSet, basename='supplier')
router.register(r'purchase-receipts', PurchaseReceiptViewSet, basename='purchase-receipt')
router.register(
    r'supplier/product-submissions',
    ProductSubmissionViewSet,
    basename='product-submission',
)

urlpatterns = [
    path('', include(router.urls)),
]
