"""Branch context helpers for staff-facing modules (POS, reservations, etc.)."""
from __future__ import annotations

from accounts.models import Role
from core.exceptions import BusinessError


def resolve_operating_branch(*, user, branch_id: int | None = None):
    """
    Resolve which branch a staff user operates on.

    - Branch staff: always their assigned branch (``employee_profile``).
    - Admin / custom roles without profile: require ``branch_id`` or fall back
      to the first active branch (admin convenience).
    """
    from branches.models import Branch

    if user.role in (Role.BRANCH_MANAGER, Role.CASHIER):
        try:
            branch = user.employee_profile.branch
        except AttributeError as err:
            raise BusinessError(
                code='EMPLOYEE_PROFILE_MISSING',
                message='Perfil de empleado no encontrado',
                status_code=400,
            ) from err

        if branch_id is not None and branch_id != branch.id:
            raise BusinessError(
                code='BRANCH_MISMATCH',
                message='No puedes operar sobre otra sucursal',
                status_code=403,
                details={'branch_id': branch_id, 'assigned_branch_id': branch.id},
            )
        return branch

    if branch_id is not None:
        branch = Branch.objects.filter(pk=branch_id, is_active=True).first()
        if branch is None:
            raise BusinessError(
                code='BRANCH_NOT_FOUND',
                message='Sucursal no válida o inactiva',
                status_code=400,
                details={'branch_id': branch_id},
            )
        return branch

    if user.role == Role.ADMIN or user.is_superuser:
        branch = Branch.objects.filter(is_active=True).order_by('name').first()
        if branch is None:
            raise BusinessError(
                code='NO_BRANCHES',
                message='No hay sucursales activas configuradas',
                status_code=400,
            )
        return branch

    raise BusinessError(
        code='BRANCH_REQUIRED',
        message='Debes indicar branch_id para operar en caja',
        status_code=400,
    )


def parse_branch_id(value) -> int | None:
    """Parse optional branch_id from query/body values."""
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as err:
        raise BusinessError(
            code='INVALID_BRANCH_ID',
            message='branch_id debe ser un entero',
            status_code=400,
        ) from err
