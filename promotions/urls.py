"""
URL configuration for promotions app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from promotions.views import PromotionViewSet, ValidatePromotionView

router = DefaultRouter()
router.register(r'promotions', PromotionViewSet, basename='promotion')

urlpatterns = [
    path('promotions/validate/', ValidatePromotionView.as_view(), name='promotion-validate'),
    path('', include(router.urls)),
]
