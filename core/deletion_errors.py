"""Human-readable messages for Django deletion / integrity errors."""
from __future__ import annotations

from collections import defaultdict

from django.db import IntegrityError
from django.db.models.deletion import ProtectedError, RestrictedError


def format_protected_objects(protected_objects: set) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for obj in protected_objects:
        label = str(obj._meta.verbose_name_plural).capitalize()
        if len(grouped[label]) < 3:
            grouped[label].append(str(obj))
    return dict(grouped)


def message_for_protected_error(exc: ProtectedError) -> str:
    grouped = format_protected_objects(exc.protected_objects)
    if not grouped:
        return 'No se puede eliminar porque está referenciado por otros registros.'

    parts: list[str] = []
    total = len(exc.protected_objects)
    shown = 0
    for label, names in grouped.items():
        shown += len(names)
        if len(names) == 1:
            parts.append(f'{names[0]} ({label.lower()})')
        else:
            parts.append(f'{", ".join(names)} ({label.lower()})')

    suffix = ''
    if total > shown:
        suffix = f' y {total - shown} registro(s) más'

    return (
        f'No se puede eliminar porque está en uso: {"; ".join(parts)}{suffix}. '
        'Elimina o reasigna esos registros primero.'
    )


def message_for_restricted_error(exc: RestrictedError) -> str:
    return message_for_protected_error(exc)


def message_for_integrity_error(exc: IntegrityError) -> str:
    msg = str(exc).lower()
    if 'unique constraint' in msg or 'duplicate key' in msg:
        if 'slug' in msg:
            return 'Ya existe un registro con ese slug.'
        if 'name' in msg:
            return 'Ya existe un registro con ese nombre.'
        if 'email' in msg:
            return 'Ya existe un usuario con ese correo.'
        if 'code' in msg:
            return 'Ya existe un registro con ese código.'
        return 'Ya existe un registro con esos datos.'
    if 'foreign key constraint' in msg or 'violates foreign key' in msg:
        return 'No se puede completar la operación porque hay registros relacionados.'
    if 'not null constraint' in msg:
        return 'Faltan datos obligatorios para guardar el registro.'
    return 'Conflicto de integridad en la base de datos.'
