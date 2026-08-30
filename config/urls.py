"""
URL configuration for FashionStore project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # API v1
    path('api/v1/', include([
        path('', include('accounts.urls')),
        path('', include('branches.urls')),
        path('', include('catalog.urls')),
        path('', include('inventory.urls')),
        path('', include('suppliers.urls')),
        path('', include('promotions.urls')),
        path('', include('reservations.urls')),
        path('', include('orders.urls')),
        path('', include('payments.urls')),
        path('pos/', include('pos.urls')),
        path('ai/', include('ai.urls')),
        path('reports/', include('reports.urls')),
    ])),

    # OpenAPI Schema
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
