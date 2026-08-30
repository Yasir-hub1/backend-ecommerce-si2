"""
FashionStore configuration package.
"""
# Import Celery app so it loads when Django starts
from .celery import app as celery_app

__all__ = ('celery_app',)
