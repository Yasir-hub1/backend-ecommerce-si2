"""
Report models for FashionStore.

Stores report requests for audit and AI-generated reports.
"""
from django.db import models
from core.models import TimeStampedModel


class ReportStatus:
    """Report status constants."""
    PENDING = 'PENDING'
    PROCESSING = 'PROCESSING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'

    CHOICES = [
        (PENDING, 'Pendiente'),
        (PROCESSING, 'Procesando'),
        (COMPLETED, 'Completado'),
        (FAILED, 'Fallido'),
    ]


class ReportRequest(TimeStampedModel):
    """
    Report request model (for voice/AI-generated reports).

    Allows auditing what each user asked for and reproducing reports.
    """

    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='report_requests',
        verbose_name='Usuario',
    )

    prompt_text = models.TextField(
        'Texto del prompt',
        help_text='Solicitud original del usuario (voz transcrita)',
    )

    interpreted_spec = models.JSONField(
        'Especificación interpretada',
        default=dict,
        blank=True,
        help_text='Métrica, dimensión, filtros, rango interpretados por IA',
    )

    result = models.JSONField(
        'Resultado',
        default=dict,
        blank=True,
        help_text='Datos del reporte generado',
    )

    status = models.CharField(
        'Estado',
        max_length=20,
        choices=ReportStatus.CHOICES,
        default=ReportStatus.PENDING,
    )

    error = models.TextField('Error', blank=True)

    class Meta:
        db_table = 'report_requests'
        verbose_name = 'Solicitud de Reporte'
        verbose_name_plural = 'Solicitudes de Reporte'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.prompt_text[:50]}"
