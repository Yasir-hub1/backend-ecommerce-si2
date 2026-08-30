"""
Reusable mixins for DRF viewsets.
"""
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly

from core.permissions import HasAppPermission


class PublicReadRBACWriteMixin:
    """
    Public/authenticated read; RBAC-gated create/update/delete.

    Set ``write_permission`` on the viewset (e.g. ``catalog.products.manage``).
    """

    write_permission = ''

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAuthenticated(), HasAppPermission()]
        return [IsAuthenticatedOrReadOnly()]

    def get_required_permission(self):
        return self.write_permission


class RBACMixin:
    """All actions gated by ``permission_map`` action → permission code."""

    permission_classes = [IsAuthenticated, HasAppPermission]
    permission_map: dict[str, str] = {}

    def get_required_permission(self):
        return self.permission_map.get(self.action)


class BranchScopedQuerysetMixin:
    """Staff users only see data from their branch. Admin sees all."""

    branch_field = 'branch'

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs

        from accounts.models import Role

        if user.role == Role.ADMIN:
            return qs

        if user.role in (Role.BRANCH_MANAGER, Role.CASHIER):
            try:
                branch_id = user.employee_profile.branch_id
                return qs.filter(**{self.branch_field: branch_id})
            except Exception:
                return qs.none()

        return qs.none()


class ReferenceCountQuerysetMixin:
    """
    Annotate list/retrieve querysets with usage counts for safe-delete UX.

    Example: reference_count_fields = {'products_count': 'products'}
    """

    reference_count_fields: dict[str, str] = {}

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action in ('list', 'retrieve') and self.reference_count_fields:
            from django.db.models import Count

            qs = qs.annotate(**{
                field: Count(relation, distinct=True)
                for field, relation in self.reference_count_fields.items()
            })
        return qs
