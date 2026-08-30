"""
Helpers for application-level RBAC (RoleDefinition + AppPermission).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from accounts.models import User


def get_user_permission_codes(user: 'User') -> set[str]:
    """Return active permission codes granted to the user's role."""
    from accounts.models import AppPermission, Role

    if not user.is_authenticated:
        return set()

    if user.is_superuser or user.role == Role.ADMIN:
        return set(
            AppPermission.objects.filter(is_active=True).values_list('code', flat=True)
        )

    return set(
        AppPermission.objects.filter(
            is_active=True,
            roles__code=user.role,
            roles__is_active=True,
        ).values_list('code', flat=True)
    )


def user_has_permission(user: 'User', code: str) -> bool:
    """Check whether the user holds a specific application permission."""
    from accounts.models import Role

    if not user.is_authenticated:
        return False
    if user.is_superuser or user.role == Role.ADMIN:
        return True
    return code in get_user_permission_codes(user)


def user_has_any_permission(user: 'User', *codes: str) -> bool:
    """Check whether the user holds at least one of the given permissions."""
    from accounts.models import Role

    if user.is_superuser or user.role == Role.ADMIN:
        return True
    granted = get_user_permission_codes(user)
    return any(code in granted for code in codes)
