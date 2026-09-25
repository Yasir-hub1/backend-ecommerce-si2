"""AI assistant and recommendation services (rule-based, grounded on catalog DB)."""
from __future__ import annotations

import logging

from ai.catalog_query import (
    apply_branch_stock,
    base_product_qs,
    list_catalog_color_names,
    outfit_pick,
    search_catalog,
)
from ai.intent import ChatIntent, merge_intents, parse_intent
from catalog.models import Product
from catalog.serializers import ProductListSerializer

logger = logging.getLogger('ai.services')


def _previous_user_intent(messages: list[dict]) -> ChatIntent | None:
    """Parse the prior user turn so refinements keep color/category context."""
    user_texts = [m['content'] for m in messages if m.get('role') == 'user']
    if len(user_texts) < 2:
        return None
    colors = list_catalog_color_names()
    return parse_intent(user_texts[-2], catalog_colors=colors)


def _build_reply(
    intent: ChatIntent,
    products: list[Product],
    *,
    branch_id: int | None,
    note: str | None = None,
) -> str:
    if not products:
        bits = ', '.join(intent.clarified) if intent.clarified else intent.raw
        return (
            f'No encontré prendas que coincidan con “{bits}”. '
            'Prueba con otra categoría (poleras, camisas, pantalones), un color '
            'del catálogo o un rango de precio.'
        )

    names = ', '.join(p.name for p in products[:3])
    filters = ''
    if intent.clarified:
        filters = f' Filtré por: {", ".join(intent.clarified)}.'

    branch_note = ''
    if branch_id:
        branch_note = ' Mostrando opciones con stock en tu sucursal.'

    relax = f' {note}.' if note else ''

    if intent.wants_outfit:
        tops = sum(1 for p in products if p.category.slug in {'camisas', 'poleras', 'chaquetas', 'vestidos'})
        bottoms = sum(1 for p in products if p.category.slug in {'pantalones', 'faldas', 'shorts'})
        if tops and bottoms:
            return (
                f'Armé un look con piezas que combinan: {names}.{filters}'
                f'{branch_note}{relax} Abre cada prenda para elegir talla y color.'
            )

    if intent.wants_sizes or intent.wants_stock:
        return (
            f'Tengo estas opciones: {names}.{filters}{branch_note}{relax} '
            'Entra al detalle para ver tallas y disponibilidad exacta.'
        )

    if intent.sort == 'price_asc':
        cheapest = products[0]
        return (
            f'Las más accesibles que encontré: {names}. '
            f'La más económica es {cheapest.name} (Bs {cheapest.base_price}).'
            f'{filters}{branch_note}{relax}'
        )

    if intent.wants_gift:
        return (
            f'Ideas de regalo según tu pedido: {names}.{filters}{branch_note}{relax} '
            'Si me dices presupuesto o estilo (formal/casual) afino mejor.'
        )

    if intent.clarified:
        return (
            f'Encontré {len(products)} prenda(s) para lo que pediste: {names}.'
            f'{filters}{branch_note}{relax}'
        )

    return (
        f'Te sugiero estas prendas del catálogo: {names}.{branch_note}{relax} '
        'Puedes pedir por color, ocasión (oficina, casual, deporte) o precio.'
    )


def _suggestions(intent: ChatIntent, products: list[Product]) -> list[str]:
    tips: list[str] = []
    if products and not intent.color_names:
        tips.append('Muéstrame en negro')
    if products and intent.sort != 'price_asc':
        tips.append('Solo las más baratas')
    if not intent.occasions:
        tips.append('Algo para oficina')
    if not intent.wants_outfit:
        tips.append('Arma un look completo')
    if intent.category_slugs and 'poleras' not in intent.category_slugs:
        tips.append('Ver poleras disponibles')
    else:
        tips.append('Ver camisas oxford')
    tips.append('¿Qué hay en oferta?')
    # Dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for tip in tips:
        if tip in seen:
            continue
        seen.add(tip)
        out.append(tip)
        if len(out) >= 4:
            break
    return out


def chat_with_assistant(*, messages: list[dict], branch_id: int | None, request) -> dict:
    last_user = next(
        (m['content'] for m in reversed(messages) if m.get('role') == 'user'),
        '',
    ).strip()

    catalog_colors = list_catalog_color_names()
    current = parse_intent(last_user, catalog_colors=catalog_colors)
    previous = _previous_user_intent(messages)
    intent = merge_intents(previous, current)

    logger.info(
        'chat intent raw=%r clarified=%s branch=%s',
        last_user,
        list(intent.clarified),
        branch_id,
    )

    products, note = search_catalog(intent, branch_id=branch_id, limit=6)
    if intent.wants_outfit:
        # Widen search then pick a top/bottom mix.
        wide, wide_note = search_catalog(
            ChatIntent(
                raw=intent.raw,
                category_slugs=('camisas', 'poleras', 'pantalones', 'faldas', 'shorts', 'chaquetas'),
                color_names=intent.color_names,
                genders=intent.genders,
                sort=intent.sort,
                min_price=intent.min_price,
                max_price=intent.max_price,
                clarified=intent.clarified,
            ),
            branch_id=branch_id,
            limit=10,
        )
        products = outfit_pick(wide, limit=4) or products
        note = note or wide_note

    serialized = ProductListSerializer(
        products,
        many=True,
        context={'request': request},
    ).data

    reply = _build_reply(intent, products, branch_id=branch_id, note=note)
    suggestions = _suggestions(intent, products)

    return {
        'reply': reply,
        'suggestions': suggestions,
        'products': serialized,
        'interpreted': {
            'filters': list(intent.clarified),
            'sort': intent.sort,
            'min_price': str(intent.min_price) if intent.min_price is not None else None,
            'max_price': str(intent.max_price) if intent.max_price is not None else None,
        },
    }


def get_recommendations(*, user, branch_id: int | None, limit: int, request) -> dict:
    from ai.models import BrowsingEvent, EventType

    limit = max(1, min(limit, 20))
    products_qs = apply_branch_stock(base_product_qs(), branch_id)

    reason = 'Productos destacados del catálogo'

    if user.is_authenticated and hasattr(user, 'customer_profile'):
        viewed_ids = list(
            BrowsingEvent.objects.filter(
                customer=user.customer_profile,
                event_type=EventType.VIEW,
                product__isnull=False,
            )
            .order_by('-occurred_at')
            .values_list('product_id', flat=True)[:10]
        )

        if viewed_ids:
            category_ids = Product.objects.filter(id__in=viewed_ids).values_list(
                'category_id',
                flat=True,
            )
            products_qs = products_qs.filter(category_id__in=category_ids).exclude(
                id__in=viewed_ids,
            )
            reason = 'Basado en productos que has visto recientemente'

    if branch_id:
        reason = f'{reason} con stock en tu sucursal'

    products = list(products_qs.order_by('-created_at')[:limit])
    if not products:
        products = list(
            apply_branch_stock(base_product_qs(), branch_id).order_by('-created_at')[:limit]
        )
        reason = 'Novedades del catálogo'

    serialized = ProductListSerializer(products, many=True, context={'request': request}).data
    return {'products': serialized, 'reason': reason}
