"""AI assistant and recommendation services (rule-based, no external LLM required)."""
from django.db.models import F, Q

from catalog.models import Product
from catalog.serializers import ProductListSerializer


def chat_with_assistant(*, messages: list[dict], branch_id: int | None, request) -> dict:
    last_user = next(
        (m['content'] for m in reversed(messages) if m.get('role') == 'user'),
        '',
    ).strip()
    query = last_user.lower()

    products_qs = Product.objects.filter(is_active=True).select_related(
        'category', 'brand', 'collection',
    ).prefetch_related('images')

    if branch_id:
        from inventory.models import BranchStock

        products_qs = products_qs.filter(
            variants__branch_stocks__branch_id=branch_id,
            variants__branch_stocks__on_hand__gt=F('variants__branch_stocks__reserved'),
        ).distinct()

    if any(word in query for word in ('camisa', 'shirt', 'oxford')):
        products_qs = products_qs.filter(
            Q(name__icontains='camisa') | Q(description__icontains='camisa'),
        )
    elif any(word in query for word in ('pantalon', 'pantalón', 'jean')):
        products_qs = products_qs.filter(
            Q(name__icontains='pant') | Q(description__icontains='pant'),
        )
    elif any(word in query for word in ('vestido', 'dress')):
        products_qs = products_qs.filter(name__icontains='vest')
    elif any(word in query for word in ('precio', 'barato', 'oferta', 'promo')):
        products_qs = products_qs.order_by('base_price')
    else:
        products_qs = products_qs.order_by('-created_at')

    products = list(products_qs[:5])
    serialized = ProductListSerializer(products, many=True, context={'request': request}).data

    if products:
        names = ', '.join(p.name for p in products[:3])
        reply = (
            f'Encontré opciones que pueden interesarte: {names}. '
            'Puedes ver detalle y stock en el catálogo.'
        )
        suggestions = [
            '¿Qué tallas tienen disponibles?',
            'Muéstrame ofertas de temporada',
            'Recomiéndame algo para regalo',
        ]
    else:
        reply = (
            'No encontré productos con esos criterios. '
            'Prueba con otra prenda o revisa el catálogo por categoría.'
        )
        suggestions = ['Ver camisas', 'Ver pantalones', 'Novedades de temporada']

    return {'reply': reply, 'suggestions': suggestions, 'products': serialized}


def get_recommendations(*, user, branch_id: int | None, limit: int, request) -> dict:
    from ai.models import BrowsingEvent, EventType

    limit = max(1, min(limit, 20))
    products_qs = Product.objects.filter(is_active=True).select_related(
        'category', 'brand', 'collection',
    ).prefetch_related('images')

    reason = 'Productos destacados del catálogo'

    if user.is_authenticated and hasattr(user, 'customer_profile'):
        viewed_ids = BrowsingEvent.objects.filter(
            customer=user.customer_profile,
            event_type=EventType.VIEW,
            product__isnull=False,
        ).order_by('-occurred_at').values_list('product_id', flat=True)[:10]

        viewed = list(viewed_ids)
        if viewed:
            category_ids = Product.objects.filter(id__in=viewed).values_list('category_id', flat=True)
            products_qs = products_qs.filter(category_id__in=category_ids).exclude(id__in=viewed)
            reason = 'Basado en productos que has visto recientemente'

    if branch_id:
        products_qs = products_qs.filter(
            variants__branch_stocks__branch_id=branch_id,
            variants__branch_stocks__on_hand__gt=F('variants__branch_stocks__reserved'),
        ).distinct()
        reason = f'{reason} con stock en tu sucursal'

    products = list(products_qs.order_by('-created_at')[:limit])
    serialized = ProductListSerializer(products, many=True, context={'request': request}).data

    return {'products': serialized, 'reason': reason}
