"""
Development settings for FashionStore project.
"""
from .base import *

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Development-specific apps
INSTALLED_APPS += [
    'django_extensions',
]

# Email backend for development (console)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# CORS - allow all origins in development
CORS_ALLOW_ALL_ORIGINS = True

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
