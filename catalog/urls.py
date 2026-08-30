"""
URL configuration for catalog app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from catalog.views import (
    CategoryViewSet,
    BrandViewSet,
    SizeGroupViewSet,
    SizeViewSet,
    ColorViewSet,
    SeasonViewSet,
    CollectionViewSet,
    ProductViewSet,
    ProductVariantViewSet,
    ProductImageViewSet,
    ARAssetViewSet,
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'brands', BrandViewSet, basename='brand')
router.register(r'size-groups', SizeGroupViewSet, basename='sizegroup')
router.register(r'sizes', SizeViewSet, basename='size')
router.register(r'colors', ColorViewSet, basename='color')
router.register(r'seasons', SeasonViewSet, basename='season')
router.register(r'collections', CollectionViewSet, basename='collection')
router.register(r'products', ProductViewSet, basename='product')
router.register(r'variants', ProductVariantViewSet, basename='variant')
router.register(r'product-images', ProductImageViewSet, basename='product-image')
router.register(r'ar-assets', ARAssetViewSet, basename='ar-asset')

urlpatterns = [
    path('', include(router.urls)),
]
