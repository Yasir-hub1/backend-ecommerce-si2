"""
Celery configuration for FashionStore.
"""
import os
from celery import Celery

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

app = Celery('fashionstore')

# Load configuration from Django settings with CELERY_ prefix
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery."""
    print(f'Request: {self.request!r}')
