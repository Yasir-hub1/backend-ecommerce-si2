"""
URL configuration for branches app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from branches.views import CityViewSet, BranchViewSet

router = DefaultRouter()
router.register(r'cities', CityViewSet, basename='city')
router.register(r'branches', BranchViewSet, basename='branch')

urlpatterns = [
    path('', include(router.urls)),
]
