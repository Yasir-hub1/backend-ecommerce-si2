"""
Custom exceptions and exception handler for FashionStore API.
"""
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError, RestrictedError
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

from core.deletion_errors import (
    format_protected_objects,
    message_for_integrity_error,
    message_for_protected_error,
    message_for_restricted_error,
)


class BusinessError(Exception):
    """
    Custom exception for business logic errors.

    Example:
        raise BusinessError(
            code='INSUFFICIENT_STOCK',
            message='No hay stock suficiente para esta variante',
            status_code=409,
            details={'variant_id': 123, 'requested': 5, 'available': 2}
        )
    """

    def __init__(self, code: str, message: str, status_code: int = 400, details=None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


def _error_response(*, code: str, message: str, details=None, status_code: int) -> Response:
    return Response(
        {
            'error': {
                'code': code,
                'message': message,
                'details': details or {},
            }
        },
        status=status_code,
    )


def api_exception_handler(exc, context):
    """
    Custom exception handler for DRF that handles BusinessError
    and formats all errors consistently.

    Error response format:
    {
        "error": {
            "code": "ERROR_CODE",
            "message": "Human readable message",
            "details": {...}
        }
    }
    """
    # Handle BusinessError
    if isinstance(exc, BusinessError):
        return _error_response(
            code=exc.code,
            message=exc.message,
            details=exc.details,
            status_code=exc.status_code,
        )

    if isinstance(exc, ProtectedError):
        return _error_response(
            code='REFERENCED_ENTITY',
            message=message_for_protected_error(exc),
            details={'references': format_protected_objects(exc.protected_objects)},
            status_code=status.HTTP_409_CONFLICT,
        )

    if isinstance(exc, RestrictedError):
        return _error_response(
            code='REFERENCED_ENTITY',
            message=message_for_restricted_error(exc),
            details={'references': format_protected_objects(exc.protected_objects)},
            status_code=status.HTTP_409_CONFLICT,
        )

    if isinstance(exc, IntegrityError):
        return _error_response(
            code='INTEGRITY_ERROR',
            message=message_for_integrity_error(exc),
            status_code=status.HTTP_409_CONFLICT,
        )

    # Call DRF's default exception handler first
    response = exception_handler(exc, context)

    # If DRF handled it, format it consistently
    if response is not None:
        code = 'VALIDATION_ERROR' if response.status_code == 400 else 'ERROR'
        message = 'Error en la solicitud'
        if response.status_code == 404:
            code = 'NOT_FOUND'
        elif response.status_code == 403:
            code = 'FORBIDDEN'
            message = 'No tienes permiso para esta operación.'
        elif response.status_code == 401:
            code = 'UNAUTHORIZED'
            message = 'Debes autenticarte para acceder a este recurso.'
        elif response.status_code == 409:
            code = 'CONFLICT'

        error_data = {
            'error': {
                'code': code,
                'message': message,
                'details': response.data,
            }
        }
        response.data = error_data

    return response
