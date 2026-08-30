"""
AI and analytics models for FashionStore.

Includes:
- BrowsingEvent: User behavior tracking
- ProductEmbedding: Vector embeddings for recommendations
- ChatSession/ChatMessage: Chatbot conversations
"""
from django.db import models
from core.models import TimeStampedModel


class EventType:
    """Browsing event type constants."""
    VIEW = 'VIEW'
    SEARCH = 'SEARCH'
    ADD_CART = 'ADD_CART'
    AR_TRY = 'AR_TRY'
    RESERVE = 'RESERVE'

    CHOICES = [
        (VIEW, 'Visualización'),
        (SEARCH, 'Búsqueda'),
        (ADD_CART, 'Agregar al carrito'),
        (AR_TRY, 'Prueba AR'),
        (RESERVE, 'Reserva'),
    ]


class BrowsingEvent(TimeStampedModel):
    """
    User browsing event for recommendations and analytics.
    """

    customer = models.ForeignKey(
        'accounts.CustomerProfile',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='browsing_events',
        verbose_name='Cliente',
    )

    session_key = models.CharField(
        'Clave de sesión',
        max_length=40,
        null=True,
        blank=True,
    )

    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='browsing_events',
        verbose_name='Producto',
    )

    event_type = models.CharField(
        'Tipo de evento',
        max_length=20,
        choices=EventType.CHOICES,
    )

    query = models.CharField('Búsqueda', max_length=200, blank=True)

    occurred_at = models.DateTimeField('Ocurrido en', auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'browsing_events'
        verbose_name = 'Evento de Navegación'
        verbose_name_plural = 'Eventos de Navegación'
        ordering = ['-occurred_at']
        indexes = [
            models.Index(fields=['customer', '-occurred_at']),
            models.Index(fields=['session_key', '-occurred_at']),
        ]

    def __str__(self):
        return f"{self.event_type} - {self.product or self.query}"


class ProductEmbedding(TimeStampedModel):
    """
    Product vector embedding for similarity search.

    Requires PostgreSQL with pgvector extension.
    """

    product = models.OneToOneField(
        'catalog.Product',
        on_delete=models.CASCADE,
        related_name='embedding',
        verbose_name='Producto',
    )

    # Vector field (requires pgvector extension)
    # This will be migrated as: embedding vector(768)
    # For now, we'll use JSONField and convert it later
    embedding = models.JSONField(
        'Vector de embedding',
        default=list,
        help_text='Vector de 768 dimensiones',
    )

    model_name = models.CharField(
        'Modelo',
        max_length=100,
        default='all-MiniLM-L6-v2',
    )

    class Meta:
        db_table = 'product_embeddings'
        verbose_name = 'Embedding de Producto'
        verbose_name_plural = 'Embeddings de Producto'

    def __str__(self):
        return f"Embedding de {self.product.name}"


class ChatSession(TimeStampedModel):
    """Chatbot conversation session."""

    customer = models.ForeignKey(
        'accounts.CustomerProfile',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='chat_sessions',
        verbose_name='Cliente',
    )

    session_key = models.CharField(
        'Clave de sesión',
        max_length=40,
        null=True,
        blank=True,
    )

    started_at = models.DateTimeField('Iniciado en', auto_now_add=True)

    context = models.JSONField(
        'Contexto',
        default=dict,
        blank=True,
        help_text='Contexto de la conversación',
    )

    class Meta:
        db_table = 'chat_sessions'
        verbose_name = 'Sesión de Chat'
        verbose_name_plural = 'Sesiones de Chat'
        ordering = ['-started_at']

    def __str__(self):
        return f"Chat {self.id} - {self.customer or 'Anónimo'}"


class MessageRole:
    """Chat message role constants."""
    USER = 'USER'
    ASSISTANT = 'ASSISTANT'
    TOOL = 'TOOL'

    CHOICES = [
        (USER, 'Usuario'),
        (ASSISTANT, 'Asistente'),
        (TOOL, 'Herramienta'),
    ]


class ChatMessage(TimeStampedModel):
    """Individual message in a chat session."""

    session = models.ForeignKey(
        'ChatSession',
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='Sesión',
    )

    role = models.CharField(
        'Rol',
        max_length=20,
        choices=MessageRole.CHOICES,
    )

    content = models.TextField('Contenido')

    tool_calls = models.JSONField(
        'Llamadas a herramientas',
        default=list,
        blank=True,
    )

    class Meta:
        db_table = 'chat_messages'
        verbose_name = 'Mensaje de Chat'
        verbose_name_plural = 'Mensajes de Chat'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"
