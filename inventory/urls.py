"""
URL configuration for inventory app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from inventory.views import BranchStockViewSet, InventoryMovementViewSet

router = DefaultRouter()
router.register(r'stock', BranchStockViewSet, basename='stock')
router.register(r'movements', InventoryMovementViewSet, basename='movement')

urlpatterns = [
    path('', include(router.urls)),
]
