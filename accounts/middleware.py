"""
HTTP middleware that records mutating API actions in the bitácora.
"""
import logging

from django.http import HttpRequest, HttpResponse

from accounts.services.bitacora import MUTATING_METHODS, parse_request_payload, record_http_request

logger = logging.getLogger('accounts.bitacora')


class BitacoraMiddleware:
    """After each successful write to the API, persist who did what and when."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.method.upper() in MUTATING_METHODS:
            try:
                request._bitacora_payload = parse_request_payload(request)
            except Exception:
                request._bitacora_payload = {}
        response = self.get_response(request)
        try:
            record_http_request(request, response)
        except Exception:
            logger.exception('bitacora middleware failed')
        return response
