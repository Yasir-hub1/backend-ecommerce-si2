"""
Custom permissions for FashionStore API.
"""
from rest_framework import permissions

from accounts.services.permissions import user_has_permission, user_has_any_permission


class IsAdmin(permissions.BasePermission):
    """Allow access only to admin users."""

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'ADMIN'


class HasAppPermission(permissions.BasePermission):
    """
    Enforce application-level RBAC on a view or viewset.

    Viewsets should implement ``get_required_permission()`` returning a
    permission code for the current action, or set ``required_permission``.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        required = getattr(view, 'required_permission', None)
        if required is None and hasattr(view, 'get_required_permission'):
            required = view.get_required_permission()

        if required is None:
            return True

        return user_has_permission(request.user, required)


class HasAnyAppPermission(permissions.BasePermission):
    """Allow access if the user has at least one of ``view.required_permissions``."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        codes = getattr(view, 'required_permissions', None)
        if not codes:
            return True

        return user_has_any_permission(request.user, *codes)


class IsBranchStaff(permissions.BasePermission):
    """Allow access to branch managers and cashiers."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in ('BRANCH_MANAGER', 'CASHIER', 'ADMIN')


class IsBranchManager(permissions.BasePermission):
    """Allow access only to branch managers."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in ('BRANCH_MANAGER', 'ADMIN')


class IsCustomer(permissions.BasePermission):
    """Allow access only to customers."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in ('CUSTOMER', 'ADMIN')


class IsSameBranch(permissions.BasePermission):
    """
    Allow access only if the object belongs to the user's branch.
    Requires the view to define a get_branch method.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        # Admin can access all branches
        if request.user.role == 'ADMIN':
            return True

        # Staff can only access their branch
        if request.user.role in ('BRANCH_MANAGER', 'CASHIER'):
            if not hasattr(request.user, 'employee_profile'):
                return False

            user_branch = request.user.employee_profile.branch
            obj_branch = getattr(obj, 'branch', None)

            return obj_branch == user_branch

        return False
