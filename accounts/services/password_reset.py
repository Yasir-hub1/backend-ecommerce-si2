"""Password reset flow using cache-backed tokens."""
import logging
import secrets

from django.contrib.auth import password_validation
from django.core.cache import cache
from django.core.exceptions import ValidationError

from accounts.models import User

logger = logging.getLogger(__name__)

CACHE_PREFIX = 'pwd_reset:'
TOKEN_TTL_SECONDS = 3600


def request_password_reset(*, email: str) -> None:
    """Create reset token if user exists. Always succeeds from caller perspective."""
    try:
        user = User.objects.get(email__iexact=email.strip(), is_active=True)
    except User.DoesNotExist:
        logger.info('password reset requested for unknown email: %s', email)
        return

    token = secrets.token_urlsafe(32)
    cache.set(f'{CACHE_PREFIX}{token}', user.id, timeout=TOKEN_TTL_SECONDS)
    logger.info(
        'password reset token for %s (dev): %s',
        user.email,
        token,
    )


def confirm_password_reset(*, token: str, password: str) -> None:
    user_id = cache.get(f'{CACHE_PREFIX}{token}')
    if not user_id:
        raise ValidationError('Token inválido o expirado')

    user = User.objects.get(pk=user_id)
    password_validation.validate_password(password, user)
    user.set_password(password)
    user.save(update_fields=['password'])
    cache.delete(f'{CACHE_PREFIX}{token}')
