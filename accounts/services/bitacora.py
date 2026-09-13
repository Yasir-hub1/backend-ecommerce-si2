"""
Append-only audit log for FashionStore API actions.

The HTTP middleware records mutating requests; views may also call
``log_action`` for explicit domain events.
"""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from django.http import HttpRequest, HttpResponse

if TYPE_CHECKING:
    from accounts.models import User

logger = logging.getLogger('accounts.bitacora')

SENSITIVE_KEYS = frozenset({
    'password',
    'password_confirm',
    'old_password',
    'new_password',
    'token',
    'refresh',
    'access',
    'secret',
    'card_number',
    'cvv',
    'cvc',
    'stripe_token',
    'authorization',
})

SKIP_PATH_PREFIXES = (
    '/api/schema',
    '/admin/',
    '/static/',
    '/media/',
)

SKIP_PATH_SUBSTRINGS = (
    '/auth/refresh/',
    '/ai/events/',
    '/bitacora/',
)

MUTATING_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})

MODULE_BY_PREFIX: dict[str, str] = {
    'auth': 'accounts',
    'users': 'accounts',
    'customers': 'accounts',
    'employees': 'accounts',
    'permissions': 'rbac',
    'roles': 'rbac',
    'products': 'catalog',
    'variants': 'catalog',
    'brands': 'catalog',
    'categories': 'catalog',
    'sizes': 'catalog',
    'size-groups': 'catalog',
    'colors': 'catalog',
    'seasons': 'catalog',
    'collections': 'catalog',
    'product-images': 'catalog',
    'ar-assets': 'catalog',
    'stock': 'inventory',
    'movements': 'inventory',
    'reservations': 'reservations',
    'orders': 'orders',
    'cart': 'orders',
    'pos': 'pos',
    'payments': 'payments',
    'checkout-session': 'payments',
    'webhook': 'payments',
    'branches': 'branches',
    'cities': 'branches',
    'suppliers': 'suppliers',
    'purchase-receipts': 'suppliers',
    'promotions': 'promotions',
    'reports': 'reports',
    'ai': 'ai',
}

RESOURCE_LABELS: dict[str, str] = {
    'products': 'producto',
    'variants': 'variante',
    'brands': 'marca',
    'categories': 'categoría',
    'sizes': 'talla',
    'size-groups': 'grupo de tallas',
    'colors': 'color',
    'seasons': 'temporada',
    'collections': 'colección',
    'product-images': 'imagen de producto',
    'ar-assets': 'recurso AR',
    'stock': 'stock',
    'movements': 'movimiento de inventario',
    'reservations': 'reserva',
    'orders': 'orden',
    'cart': 'carrito',
    'sales': 'venta POS',
    'users': 'usuario',
    'customers': 'cliente',
    'employees': 'empleado',
    'permissions': 'permiso',
    'roles': 'rol',
    'branches': 'sucursal',
    'cities': 'ciudad',
    'suppliers': 'proveedor',
    'purchase-receipts': 'recepción de compra',
    'promotions': 'promoción',
    'reports': 'reporte',
    'login': 'sesión',
    'register': 'cuenta',
}

_OBJECT_ID_RE = re.compile(r'^[0-9]+$|^[0-9a-fA-F-]{8,}$')


def log_action(
    *,
    action: str,
    module: str,
    description: str,
    user: User | None = None,
    resource: str = '',
    object_id: str = '',
    method: str = '',
    path: str = '',
    ip_address: str | None = None,
    metadata: dict[str, Any] | None = None,
    user_email: str = '',
    user_full_name: str = '',
) -> None:
    """Persist one bitácora row. Failures are logged, never raised."""
    from accounts.models import Bitacora

    email = user_email
    full_name = user_full_name
    if user is not None:
        email = email or (user.email or '')
        full_name = full_name or user.get_full_name()

    try:
        Bitacora.objects.create(
            user=user if getattr(user, 'pk', None) else None,
            user_email=email[:254],
            user_full_name=full_name[:160],
            action=action,
            module=module[:50],
            resource=resource[:80],
            object_id=str(object_id)[:64] if object_id else '',
            description=description,
            method=method[:10],
            path=path[:255],
            ip_address=ip_address or None,
            metadata=sanitize_payload(metadata or {}),
        )
    except Exception:
        logger.exception('failed to write bitacora entry')


def record_http_request(request: HttpRequest, response: HttpResponse) -> None:
    """Record a mutating API request after the view has run."""
    try:
        if not _should_record(request, response):
            return

        path = request.path
        method = request.method.upper()
        payload = getattr(request, '_bitacora_payload', None)
        if not isinstance(payload, dict):
            payload = parse_request_payload(request)
        status_code = getattr(response, 'status_code', 0)
        action = _action_from_request(path, method, status_code)
        module, resource, url_object_id = _parse_path(path)
        object_id = url_object_id or _object_id_from_response(response)
        user = _resolve_user(request)
        email_hint = ''
        if user is None:
            user, email_hint = _user_from_payload_or_response(payload, response)

        description = _describe(action, resource, object_id, path, method)
        metadata: dict[str, Any] = {
            'status_code': status_code,
            'query': dict(request.GET.items()) if request.GET else {},
        }
        body = sanitize_payload(payload)
        if body:
            metadata['body'] = body

        log_action(
            action=action,
            module=module,
            description=description,
            user=user,
            resource=resource,
            object_id=object_id,
            method=method,
            path=path,
            ip_address=_client_ip(request),
            metadata=metadata,
            user_email=email_hint,
            user_full_name='',
        )
    except Exception:
        logger.exception('failed to record bitacora from HTTP request')


def sanitize_payload(value: Any) -> Any:
    """Drop secrets and truncate large structures for storage."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                cleaned[key] = '[redacted]'
            else:
                cleaned[key] = sanitize_payload(item)
        return cleaned
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value[:30]]
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + '…'
    return value


def _should_record(request: HttpRequest, response: HttpResponse) -> bool:
    method = request.method.upper()
    if method not in MUTATING_METHODS:
        return False

    path = request.path
    if not path.startswith('/api/'):
        return False
    if any(path.startswith(prefix) for prefix in SKIP_PATH_PREFIXES):
        return False
    if any(fragment in path for fragment in SKIP_PATH_SUBSTRINGS):
        return False

    status_code = getattr(response, 'status_code', 0)
    if '/auth/login/' in path:
        return 200 <= status_code < 500
    return 200 <= status_code < 400


def _action_from_request(path: str, method: str, status_code: int) -> str:
    from accounts.models import BitacoraAction

    if '/auth/login/' in path:
        if 200 <= status_code < 300:
            return BitacoraAction.LOGIN
        return BitacoraAction.LOGIN_FAILED
    if '/auth/register/' in path:
        return BitacoraAction.REGISTER
    if method == 'POST':
        return BitacoraAction.CREATE
    if method in ('PUT', 'PATCH'):
        return BitacoraAction.UPDATE
    if method == 'DELETE':
        return BitacoraAction.DELETE
    return BitacoraAction.OTHER


def _parse_path(path: str) -> tuple[str, str, str]:
    """Return (module, resource, object_id) from an API path."""
    trimmed = path.split('?')[0].strip('/')
    parts = [p for p in trimmed.split('/') if p]
    if len(parts) >= 2 and parts[0] == 'api' and parts[1].startswith('v'):
        parts = parts[2:]
    if not parts:
        return 'core', '', ''

    prefix = parts[0]
    module = MODULE_BY_PREFIX.get(prefix, prefix)
    resource = prefix
    object_id = ''

    if prefix in ('pos', 'ai', 'reports') and len(parts) > 1:
        resource = parts[1]

    for segment in reversed(parts):
        if _OBJECT_ID_RE.match(segment) and segment not in ('v1',):
            object_id = segment
            break

    if object_id:
        try:
            idx = parts.index(object_id)
            if idx > 0:
                resource = parts[idx - 1]
        except ValueError:
            pass

    return module, resource, object_id


def _describe(action: str, resource: str, object_id: str, path: str, method: str) -> str:
    from accounts.models import BitacoraAction

    label = RESOURCE_LABELS.get(resource, resource.replace('-', ' ') or 'recurso')
    target = f'{label} #{object_id}' if object_id else label

    verbs = {
        BitacoraAction.CREATE: f'Creó {target}',
        BitacoraAction.UPDATE: f'Actualizó {target}',
        BitacoraAction.DELETE: f'Eliminó {target}',
        BitacoraAction.LOGIN: 'Inició sesión',
        BitacoraAction.LOGIN_FAILED: 'Intento de inicio de sesión fallido',
        BitacoraAction.REGISTER: 'Registró una cuenta',
        BitacoraAction.OTHER: f'Ejecutó {method} sobre {target}',
    }
    description = verbs.get(action, f'{method} {path}')
    custom = _custom_action_name(path, object_id)
    if custom and action in (BitacoraAction.CREATE, BitacoraAction.OTHER):
        return f'Ejecutó {custom} en {target}'
    return description


def _custom_action_name(path: str, object_id: str) -> str:
    parts = [p for p in path.strip('/').split('/') if p]
    if not parts:
        return ''
    last = parts[-1]
    if last and last != object_id and not _OBJECT_ID_RE.match(last):
        if last not in MODULE_BY_PREFIX and last not in ('api', 'v1', 'auth'):
            return last.replace('-', ' ').replace('_', ' ')
    return ''


def _resolve_user(request: HttpRequest) -> User | None:
    user = getattr(request, 'user', None)
    if user is not None and getattr(user, 'is_authenticated', False):
        return user
    return None


def parse_request_payload(request: HttpRequest) -> dict[str, Any]:
    """Read and cache a sanitized JSON/form snapshot before the view runs."""
    content_type = (request.META.get('CONTENT_TYPE') or '').lower()
    if 'multipart/form-data' in content_type:
        return {'multipart': True}
    try:
        raw = request.body
        if not raw:
            return {}
        if 'application/json' in content_type or raw[:1] in (b'{', b'['):
            parsed = json.loads(raw.decode('utf-8'))
            return parsed if isinstance(parsed, dict) else {'value': parsed}
        return {}
    except Exception:
        return {}


def _user_from_payload_or_response(
    payload: dict[str, Any],
    response: HttpResponse,
) -> tuple[User | None, str]:
    from accounts.models import User

    raw_email = payload.get('email') or payload.get('username')
    email_hint = raw_email.strip().lower() if isinstance(raw_email, str) else ''
    user = User.objects.filter(email__iexact=email_hint).first() if email_hint else None
    if user is not None:
        return user, email_hint

    try:
        content = response.content
        if content and len(content) <= 20_000:
            body = json.loads(content.decode('utf-8'))
            user_data = body.get('user') if isinstance(body, dict) else None
            if isinstance(user_data, dict):
                email = str(user_data.get('email') or email_hint)
                uid = user_data.get('id')
                if uid is not None:
                    user = User.objects.filter(pk=uid).first()
                if user is None and email:
                    user = User.objects.filter(email__iexact=email).first()
                return user, email
    except Exception:
        pass
    return None, email_hint


def _object_id_from_response(response: HttpResponse) -> str:
    try:
        content = response.content
        if not content or len(content) > 20_000:
            return ''
        payload = json.loads(content.decode('utf-8'))
        if isinstance(payload, dict) and payload.get('id') is not None:
            return str(payload['id'])
        user = payload.get('user') if isinstance(payload, dict) else None
        if isinstance(user, dict) and user.get('id') is not None:
            return str(user['id'])
    except Exception:
        return ''
    return ''


def _client_ip(request: HttpRequest) -> str | None:
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()[:45]
    ip = request.META.get('REMOTE_ADDR')
    return ip[:45] if ip else None
