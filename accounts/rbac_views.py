"""
Views for RBAC management (roles and permissions).
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from accounts.models import AppPermission, RoleDefinition, Role
from accounts.rbac_serializers import (
    AppPermissionSerializer,
    RoleDefinitionSerializer,
    RoleDefinitionWriteSerializer,
    RolePermissionAssignSerializer,
    UserPermissionsSerializer,
)
from core.permissions import HasAppPermission


class AppPermissionViewSet(viewsets.ModelViewSet):
    """
    CRUD for application permissions.

    Requires ``rbac.permissions.manage`` for write operations.
    Requires ``rbac.permissions.view`` for read operations.
    """

    queryset = AppPermission.objects.all()
    serializer_class = AppPermissionSerializer
    permission_classes = [IsAuthenticated, HasAppPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['module', 'is_active']
    search_fields = ['code', 'name', 'description']
    ordering_fields = ['module', 'code', 'name', 'created_at']
    ordering = ['module', 'code']
    permission_map = {
        'list': 'rbac.permissions.view',
        'retrieve': 'rbac.permissions.view',
        'create': 'rbac.permissions.manage',
        'update': 'rbac.permissions.manage',
        'partial_update': 'rbac.permissions.manage',
        'destroy': 'rbac.permissions.manage',
    }

    def get_required_permission(self):
        return self.permission_map.get(self.action)


class RoleDefinitionViewSet(viewsets.ModelViewSet):
    """
    CRUD for role definitions and their permission sets.

    Requires ``rbac.roles.manage`` for write operations.
    Requires ``rbac.roles.view`` for read operations.
    """

    queryset = RoleDefinition.objects.prefetch_related('permissions').all()
    permission_classes = [IsAuthenticated, HasAppPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'is_system']
    search_fields = ['code', 'name', 'description']
    ordering_fields = ['name', 'code', 'created_at']
    ordering = ['name']
    permission_map = {
        'list': 'rbac.roles.view',
        'retrieve': 'rbac.roles.view',
        'create': 'rbac.roles.manage',
        'update': 'rbac.roles.manage',
        'partial_update': 'rbac.roles.manage',
        'destroy': 'rbac.roles.manage',
        'assign_permissions': 'rbac.roles.manage',
        'add_permissions': 'rbac.roles.manage',
        'remove_permissions': 'rbac.roles.manage',
    }

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return RoleDefinitionWriteSerializer
        return RoleDefinitionSerializer

    def get_required_permission(self):
        return self.permission_map.get(self.action)

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        if role.is_system:
            return Response(
                {'detail': 'No se puede eliminar un rol del sistema'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['put'], url_path='permissions')
    def assign_permissions(self, request, pk=None):
        """
        Replace all permissions assigned to a role.

        PUT /api/v1/roles/{id}/permissions/
        Body: { "permission_ids": [1, 2, 3] }
        """
        role = self.get_object()
        serializer = RolePermissionAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role.permissions.set(serializer.validated_data['permission_ids'])
        return Response(RoleDefinitionSerializer(role).data)

    @action(detail=True, methods=['post'], url_path='permissions/add')
    def add_permissions(self, request, pk=None):
        """
        Add permissions to a role without removing existing ones.

        POST /api/v1/roles/{id}/permissions/add/
        Body: { "permission_ids": [4, 5] }
        """
        role = self.get_object()
        serializer = RolePermissionAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role.permissions.add(*serializer.validated_data['permission_ids'])
        return Response(RoleDefinitionSerializer(role).data)

    @action(detail=True, methods=['post'], url_path='permissions/remove')
    def remove_permissions(self, request, pk=None):
        """
        Remove permissions from a role.

        POST /api/v1/roles/{id}/permissions/remove/
        Body: { "permission_ids": [4, 5] }
        """
        role = self.get_object()
        serializer = RolePermissionAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role.permissions.remove(*serializer.validated_data['permission_ids'])
        return Response(RoleDefinitionSerializer(role).data)


class CurrentUserPermissionsView(APIView):
    """
    Return permissions for the authenticated user.

    Used by the frontend to build menus and guard routes.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        codes = user.get_permission_codes()
        permissions = AppPermission.objects.filter(
            code__in=codes, is_active=True
        ).order_by('module', 'code')
        role_def = RoleDefinition.objects.filter(code=user.role, is_active=True).first()
        role_name = role_def.name if role_def else dict(Role.CHOICES).get(user.role, user.role)

        payload = {
            'role': user.role,
            'role_name': role_name,
            'permissions': permissions,
            'permission_codes': codes,
        }
        return Response(UserPermissionsSerializer(payload).data)
