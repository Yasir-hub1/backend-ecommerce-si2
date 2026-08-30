"""
URL configuration for orders app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from orders.views import CartViewSet, OrderViewSet
from pos.views import POSSaleView

router = DefaultRouter()
router.register(r'cart', CartViewSet, basename='cart')
router.register(r'orders', OrderViewSet, basename='order')

urlpatterns = [
    # Legacy alias — prefer POST /api/v1/pos/sales/checkout/
    path('pos/sales/', POSSaleView.as_view(), name='pos-sale-legacy'),

    # Router URLs
    path('', include(router.urls)),
]
