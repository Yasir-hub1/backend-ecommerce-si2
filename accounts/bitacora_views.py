"""
Read-only API for the system bitácora (admin audit log).
"""
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated

from accounts.models import Bitacora
from accounts.serializers import BitacoraSerializer
from core.permissions import HasAppPermission


class BitacoraFilter(django_filters.FilterSet):
    """Filter bitácora by actor, action, module and date range."""

    created_from = django_filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_to = django_filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='lte')
    user_email = django_filters.CharFilter(field_name='user_email', lookup_expr='icontains')

    class Meta:
        model = Bitacora
        fields = ['user', 'action', 'module']


class BitacoraViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Consulta de la bitácora de acciones.

    Requiere ``bitacora.view``. Las entradas no se editan ni eliminan.
    """

    serializer_class = BitacoraSerializer
    permission_classes = [IsAuthenticated, HasAppPermission]
    required_permission = 'bitacora.view'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = BitacoraFilter
    search_fields = ['user_email', 'user_full_name', 'description', 'path', 'resource']
    ordering_fields = ['created_at', 'action', 'module']
    ordering = ['-created_at']

    def get_queryset(self):
        return Bitacora.objects.select_related('user').all()
