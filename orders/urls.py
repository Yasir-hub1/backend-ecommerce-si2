"""
URL configuration for orders app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from orders.views import CartViewSet, OrderViewSet

router = DefaultRouter()
router.register(r'cart', CartViewSet, basename='cart')
router.register(r'orders', OrderViewSet, basename='order')

urlpatterns = [
    # Router URLs
    path('', include(router.urls)),
]
