"""
Views for branches app.
"""
from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from branches.models import City, Branch
from branches.serializers import CitySerializer, BranchSerializer, BranchListSerializer
from core.mixins import PublicReadRBACWriteMixin


class CityViewSet(PublicReadRBACWriteMixin, viewsets.ModelViewSet):
    """
    City management (RF03).

    Public read for registration and reservations; RBAC write for admin.
    """

    queryset = City.objects.filter(is_active=True).order_by('department', 'name')
    serializer_class = CitySerializer
    write_permission = 'branches.manage'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['department', 'is_active']
    search_fields = ['name', 'department']
    ordering = ['department', 'name']

    def get_queryset(self):
        from accounts.models import Role
        if (
            self.request.user.is_authenticated
            and getattr(self.request.user, 'role', None) == Role.ADMIN
        ):
            return City.objects.all().order_by('department', 'name')
        return City.objects.filter(is_active=True).order_by('department', 'name')


class BranchViewSet(PublicReadRBACWriteMixin, viewsets.ModelViewSet):
    """
    Branch management (RF03).

    Multi-branch fashion store locations with fitting rooms and hours.
    """

    queryset = Branch.objects.select_related('city').filter(is_active=True)
    serializer_class = BranchSerializer
    write_permission = 'branches.manage'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['city', 'is_active']
    search_fields = ['name', 'code', 'address']
    ordering = ['city__department', 'name']

    def get_serializer_class(self):
        if self.action == 'list':
            return BranchListSerializer
        return BranchSerializer

    def get_queryset(self):
        from accounts.models import Role
        if (
            self.request.user.is_authenticated
            and getattr(self.request.user, 'role', None) == Role.ADMIN
        ):
            return Branch.objects.select_related('city').all()
        return Branch.objects.select_related('city').filter(is_active=True)
