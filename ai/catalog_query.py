"""Apply ChatIntent filters to the FashionStore catalog queryset."""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db.models import F, Prefetch, Q, QuerySet

from ai.intent import ChatIntent
from catalog.models import Color, Product, ProductImage

logger = logging.getLogger('ai.catalog_query')


def base_product_qs() -> QuerySet[Product]:
    return (
        Product.objects.filter(is_active=True)
        .select_related('category', 'brand', 'collection')
        .prefetch_related(
            Prefetch(
                'images',
                queryset=ProductImage.objects.order_by('-is_primary', 'id'),
            ),
        )
    )


def apply_branch_stock(qs: QuerySet[Product], branch_id: int | None) -> QuerySet[Product]:
    if not branch_id:
        return qs
    return qs.filter(
        variants__branch_stocks__branch_id=branch_id,
        variants__branch_stocks__on_hand__gt=F('variants__branch_stocks__reserved'),
    ).distinct()


def apply_intent(qs: QuerySet[Product], intent: ChatIntent) -> QuerySet[Product]:
    """Filter and sort products according to the interpreted intent."""
    if intent.category_slugs:
        qs = qs.filter(category__slug__in=intent.category_slugs)

    if intent.genders:
        # UNISEX always allowed alongside an explicit gender ask.
        genders = set(intent.genders)
        if 'MALE' in genders or 'FEMALE' in genders:
            genders.add('UNISEX')
        qs = qs.filter(gender__in=genders)

    if intent.color_names:
        color_q = Q()
        for name in intent.color_names:
            color_q |= Q(variants__color__name__iexact=name)
            color_q |= Q(variants__color__slug__icontains=name.lower().replace(' ', '-'))
            color_q |= Q(name__icontains=name)
            color_q |= Q(description__icontains=name)
        qs = qs.filter(color_q).distinct()

    if intent.brand_keywords:
        brand_q = Q()
        for kw in intent.brand_keywords:
            brand_q |= Q(brand__name__icontains=kw)
            brand_q |= Q(name__icontains=kw)
        qs = qs.filter(brand_q)

    if intent.min_price is not None:
        qs = qs.filter(base_price__gte=intent.min_price)
    if intent.max_price is not None:
        qs = qs.filter(base_price__lte=intent.max_price)

    if intent.search_terms and not (
        intent.category_slugs or intent.color_names or intent.brand_keywords
    ):
        term_q = Q()
        for term in intent.search_terms:
            term_q |= (
                Q(name__icontains=term)
                | Q(description__icontains=term)
                | Q(material__icontains=term)
                | Q(category__name__icontains=term)
            )
        qs = qs.filter(term_q)
    elif intent.search_terms and intent.category_slugs:
        # Soft boost: prefer name hits but don't exclude the whole category.
        pass

    if intent.sort == 'price_asc':
        qs = qs.order_by('base_price', 'name')
    elif intent.sort == 'price_desc':
        qs = qs.order_by('-base_price', 'name')
    elif intent.sort == 'newest':
        qs = qs.order_by('-created_at')
    else:
        # Soft relevance: prefer matches on name, then newest.
        qs = qs.order_by('-created_at')

    return qs


def search_catalog(
    intent: ChatIntent,
    *,
    branch_id: int | None,
    limit: int = 6,
) -> tuple[list[Product], str | None]:
    """
    Run the intent against the DB.

    Returns (products, relaxation_note). relaxation_note is set when we had to
    drop a filter (e.g. no stock in the requested color).
    """
    limit = max(1, min(limit, 12))
    qs = apply_branch_stock(base_product_qs(), branch_id)
    filtered = apply_intent(qs, intent)
    products = list(filtered[:limit])

    if products:
        logger.debug('catalog hit intent=%s count=%s', intent.clarified, len(products))
        return products, None

    # Fallback 1: drop free-text terms, keep structured filters
    if intent.search_terms:
        relaxed = ChatIntent(
            raw=intent.raw,
            category_slugs=intent.category_slugs,
            category_keywords=intent.category_keywords,
            color_names=intent.color_names,
            brand_keywords=intent.brand_keywords,
            genders=intent.genders,
            search_terms=(),
            occasions=intent.occasions,
            min_price=intent.min_price,
            max_price=intent.max_price,
            sort=intent.sort,
            wants_sizes=intent.wants_sizes,
            wants_stock=intent.wants_stock,
            wants_gift=intent.wants_gift,
            wants_outfit=intent.wants_outfit,
            clarified=intent.clarified,
        )
        products = list(apply_intent(qs, relaxed)[:limit])
        if products:
            return products, None

    # Fallback 2: keep category/gender/price, drop color (common: asked color not stocked)
    if intent.color_names and (intent.category_slugs or intent.genders):
        soft = ChatIntent(
            raw=intent.raw,
            category_slugs=intent.category_slugs,
            genders=intent.genders,
            brand_keywords=intent.brand_keywords,
            min_price=intent.min_price,
            max_price=intent.max_price,
            sort=intent.sort,
            clarified=intent.clarified,
        )
        products = list(apply_intent(qs, soft)[:limit])
        if products:
            color_label = ', '.join(intent.color_names)
            return products, f'No había stock en {color_label}; te muestro la categoría pedida'

    # Fallback 3: category alone
    if intent.category_slugs:
        soft = ChatIntent(
            raw=intent.raw,
            category_slugs=intent.category_slugs,
            sort=intent.sort or 'newest',
            clarified=intent.clarified,
        )
        products = list(apply_intent(qs, soft)[:limit])
        if products:
            return products, 'Aflojé algunos filtros para mostrarte opciones cercanas'

    # Fallback 4: popular / newest in branch
    logger.debug('catalog miss — returning newest for intent=%s', intent.raw)
    return list(qs.order_by('-created_at')[:limit]), 'No coincidió el filtro; estas son novedades del catálogo'


def list_catalog_color_names() -> list[str]:
    return list(Color.objects.order_by('name').values_list('name', flat=True))


def outfit_pick(products: list[Product], limit: int = 4) -> list[Product]:
    """Prefer a top + bottom mix when the user asks for a complete look."""
    tops_slugs = {'camisas', 'poleras', 'chaquetas', 'vestidos'}
    bottoms_slugs = {'pantalones', 'faldas', 'shorts'}
    tops = [p for p in products if p.category.slug in tops_slugs]
    bottoms = [p for p in products if p.category.slug in bottoms_slugs]
    mixed: list[Product] = []
    for bucket in (tops, bottoms):
        for item in bucket:
            if item not in mixed:
                mixed.append(item)
            if len(mixed) >= limit:
                return mixed
    for item in products:
        if item not in mixed:
            mixed.append(item)
        if len(mixed) >= limit:
            break
    return mixed
