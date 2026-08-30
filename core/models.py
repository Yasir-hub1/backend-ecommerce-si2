"""
Core models and base classes for FashionStore.
"""
import random
import string
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """
    Abstract base model that provides self-updating
    'created_at' and 'updated_at' fields.
    """
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']


class CodeGeneratorMixin:
    """
    Mixin to generate unique codes for models like Order, Reservation, etc.

    Usage:
        class Order(CodeGeneratorMixin, TimeStampedModel):
            code = models.CharField(max_length=14, unique=True, editable=False)
            code_prefix = 'ORD'  # Override this in your model
            code_length = 8      # Override this in your model
    """
    code_prefix = 'CODE'
    code_length = 8

    @classmethod
    def generate_code(cls):
        """Generate a unique code with the format: PREFIX-XXXXXX"""
        while True:
            random_part = ''.join(random.choices(
                string.ascii_uppercase + string.digits,
                k=cls.code_length
            ))
            code = f"{cls.code_prefix}-{random_part}"

            # Check if code already exists
            if not cls.objects.filter(code=code).exists():
                return code

    def save(self, *args, **kwargs):
        """Auto-generate code if not set."""
        if not self.code:
            self.code = self.generate_code()
        super().save(*args, **kwargs)
