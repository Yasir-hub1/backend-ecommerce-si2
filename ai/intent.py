"""Rule-based NLU for FashionStore chat — interprets Spanish shopping intents."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from typing import Literal

SortKey = Literal['relevance', 'price_asc', 'price_desc', 'newest']


def _norm(text: str) -> str:
    """Lowercase + strip accents for robust matching."""
    decomposed = unicodedata.normalize('NFD', text.lower().strip())
    return ''.join(ch for ch in decomposed if unicodedata.category(ch) != 'Mn')


@dataclass(frozen=True)
class ChatIntent:
    """Structured interpretation of a shopper message."""

    raw: str
    category_slugs: tuple[str, ...] = ()
    category_keywords: tuple[str, ...] = ()
    color_names: tuple[str, ...] = ()
    brand_keywords: tuple[str, ...] = ()
    genders: tuple[str, ...] = ()
    search_terms: tuple[str, ...] = ()
    occasions: tuple[str, ...] = ()
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    sort: SortKey = 'relevance'
    wants_sizes: bool = False
    wants_stock: bool = False
    wants_gift: bool = False
    wants_outfit: bool = False
    clarified: tuple[str, ...] = ()  # human-readable filters for the reply


# Category aliases → catalog slug(s)
_CATEGORY_ALIASES: dict[str, tuple[str, ...]] = {
    'camisa': ('camisas',),
    'camisas': ('camisas',),
    'shirt': ('camisas',),
    'oxford': ('camisas',),
    'pantalon': ('pantalones',),
    'pantalones': ('pantalones',),
    'jean': ('pantalones',),
    'jeans': ('pantalones',),
    'chino': ('pantalones',),
    'vestido': ('vestidos',),
    'vestidos': ('vestidos',),
    'falda': ('faldas',),
    'faldas': ('faldas',),
    'chaqueta': ('chaquetas',),
    'chaquetas': ('chaquetas',),
    'chamarra': ('chaquetas',),
    'denim': ('chaquetas', 'pantalones'),
    'polera': ('poleras',),
    'poleras': ('poleras',),
    'remera': ('poleras',),
    'playera': ('poleras',),
    'tshirt': ('poleras',),
    'short': ('shorts',),
    'shorts': ('shorts',),
    'calzado': ('calzado',),
    'zapato': ('calzado',),
    'zapatilla': ('calzado',),
    'zapatillas': ('calzado',),
    'tenis': ('calzado',),
    'accesorio': ('accesorios',),
    'accesorios': ('accesorios',),
    'cinturon': ('accesorios',),
    'cinto': ('accesorios',),
    'ropa interior': ('ropa-interior',),
    'interior': ('ropa-interior',),
}

_COLOR_ALIASES: dict[str, tuple[str, ...]] = {
    'negro': ('Negro',),
    'negra': ('Negro',),
    'negros': ('Negro',),
    'negras': ('Negro',),
    'black': ('Negro',),
    'blanco': ('Blanco',),
    'blanca': ('Blanco',),
    'blancos': ('Blanco',),
    'blancas': ('Blanco',),
    'white': ('Blanco',),
    'azul': ('Azul Marino',),
    'azules': ('Azul Marino',),
    'marino': ('Azul Marino',),
    'navy': ('Azul Marino',),
    'rojo': ('Rojo',),
    'roja': ('Rojo',),
    'rojos': ('Rojo',),
    'rojas': ('Rojo',),
    'red': ('Rojo',),
    'gris': ('Gris Melange',),
    'grises': ('Gris Melange',),
    'gray': ('Gris Melange',),
    'grey': ('Gris Melange',),
    'beige': ('Beige',),
    'verde': ('Verde Oliva',),
    'verdes': ('Verde Oliva',),
    'oliva': ('Verde Oliva',),
    'rosa': ('Rosa Palo',),
    'rosas': ('Rosa Palo',),
    'pink': ('Rosa Palo',),
    'mostaza': ('Mostaza',),
    'bordo': ('Borgoña',),
    'borgona': ('Borgoña',),
    'burgundy': ('Borgoña',),
}

_GENDER_ALIASES: dict[str, tuple[str, ...]] = {
    'hombre': ('MALE',),
    'hombres': ('MALE',),
    'caballero': ('MALE',),
    'masculino': ('MALE',),
    'mujer': ('FEMALE',),
    'mujeres': ('FEMALE',),
    'dama': ('FEMALE',),
    'femenino': ('FEMALE',),
    'nina': ('KIDS',),
    'nino': ('KIDS',),
    'ninos': ('KIDS',),
    'kids': ('KIDS',),
    'infantil': ('KIDS',),
    'unisex': ('UNISEX',),
}

_OCCASION_CATEGORIES: dict[str, tuple[str, ...]] = {
    'oficina': ('camisas', 'pantalones', 'chaquetas'),
    'trabajo': ('camisas', 'pantalones', 'chaquetas'),
    'formal': ('camisas', 'pantalones', 'vestidos', 'chaquetas'),
    'reunion': ('camisas', 'pantalones'),
    'casual': ('poleras', 'pantalones', 'shorts'),
    'finde': ('poleras', 'shorts', 'calzado'),
    'deporte': ('shorts', 'calzado', 'poleras'),
    'gym': ('shorts', 'poleras', 'calzado'),
    'sport': ('shorts', 'poleras', 'calzado'),
    'verano': ('shorts', 'vestidos', 'poleras'),
    'invierno': ('chaquetas', 'pantalones'),
    'escolar': ('faldas', 'camisas', 'pantalones'),
}

_OCCASION_KEYWORDS: dict[str, tuple[str, ...]] = {
    'oficina': ('oficina', 'oxford', 'chino', 'classic', 'slim'),
    'formal': ('oxford', 'classic', 'midi', 'cuero'),
    'casual': ('basica', 'urban', 'cotidian'),
    'deporte': ('deportivo', 'run', 'sport', 'sportiva'),
    'regalo': (),
}

_STOPWORDS = frozenset({
    'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'de', 'del', 'al',
    'y', 'o', 'que', 'para', 'por', 'con', 'sin', 'en', 'mi', 'me', 'te',
    'algo', 'alguna', 'algun', 'busco', 'quiero', 'necesito', 'mostrar',
    'muestrame', 'dame', 'hay', 'tienen', 'tiene', 'puedes', 'recomienda',
    'recomendame', 'recomiendas', 'sugiere', 'ver', 'mas', 'muy', 'como',
    'hola', 'porfa', 'porfavor', 'gracias', 'este', 'esta', 'ese', 'esa',
    'lo', 'le', 'barato', 'barata', 'baratos', 'baratas', 'economico',
    'economica', 'oferta', 'promo', 'caro', 'cara', 'deportivo', 'deportiva',
    'deportivos', 'deportivas', 'completo', 'completa', 'arma', 'armame',
})

_PRICE_MAX_RE = re.compile(
    r'(?:menos\s+de|hasta|bajo|maximo|máximo|max\.?)\s*(?:bs\.?\s*)?(\d+(?:[.,]\d+)?)',
    re.IGNORECASE,
)
_PRICE_MIN_RE = re.compile(
    r'(?:mas\s+de|desde|arriba\s+de|minimo|mínimo|min\.?)\s*(?:bs\.?\s*)?(\d+(?:[.,]\d+)?)',
    re.IGNORECASE,
)
_PRICE_AROUND_RE = re.compile(
    r'(?:alrededor\s+de|cerca\s+de|unos?)\s*(?:bs\.?\s*)?(\d+(?:[.,]\d+)?)',
    re.IGNORECASE,
)


def _parse_decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(',', '.'))
    except (InvalidOperation, AttributeError):
        return None


def _unique(seq: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for item in seq:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return tuple(out)


def parse_intent(message: str, *, catalog_colors: list[str] | None = None) -> ChatIntent:
    """Extract shopping filters from a natural-language message."""
    raw = message.strip()
    text = _norm(raw)
    clarified: list[str] = []

    category_slugs: list[str] = []
    category_keywords: list[str] = []
    for alias, slugs in _CATEGORY_ALIASES.items():
        if alias in text:
            category_slugs.extend(slugs)
            category_keywords.append(alias)
    if category_slugs:
        # One human label per matched category family
        clarified.extend(sorted(set(category_slugs)))

    color_names: list[str] = []
    for alias, names in _COLOR_ALIASES.items():
        if re.search(rf'\b{re.escape(alias)}\b', text):
            color_names.extend(names)
            clarified.append(names[0].lower())

    # Match real color names from DB that weren't covered by aliases
    if catalog_colors:
        for name in catalog_colors:
            n = _norm(name)
            if len(n) >= 3 and re.search(rf'\b{re.escape(n)}\b', text):
                color_names.append(name)
                clarified.append(name.lower())

    genders: list[str] = []
    for alias, codes in _GENDER_ALIASES.items():
        if re.search(rf'\b{re.escape(alias)}\b', text):
            genders.extend(codes)
            clarified.append(alias)

    occasions: list[str] = []
    for occasion, slugs in _OCCASION_CATEGORIES.items():
        if occasion in text:
            occasions.append(occasion)
            category_slugs.extend(slugs)
            clarified.append(occasion)

    brand_keywords: list[str] = []
    for brand in (
        'urban fit', 'urban', 'sportiva', 'zara', 'denim', 'classic man',
        'luna rosa', 'andes', 'altiplano', 'tropicana', 'kids moda',
    ):
        if brand in text:
            brand_keywords.append(brand)
            clarified.append(brand)

    wants_gift = any(w in text for w in ('regalo', 'gift', 'presente'))
    wants_outfit = any(
        w in text for w in ('look', 'outfit', 'conjunto', 'completo', 'combinar')
    )
    wants_sizes = any(w in text for w in ('talla', 'talle', 'size', 'medida'))
    wants_stock = any(w in text for w in ('stock', 'disponible', 'disponibilidad', 'hay'))

    sort: SortKey = 'relevance'
    if any(w in text for w in ('barato', 'barata', 'economico', 'economica', 'oferta', 'promo', 'rebaja')):
        sort = 'price_asc'
        clarified.append('precio bajo')
    elif any(w in text for w in ('caro', 'cara', 'premium', 'lujo')):
        sort = 'price_desc'
        clarified.append('precio alto')
    elif any(w in text for w in ('nuevo', 'nueva', 'novedad', 'tendencia', 'recien')):
        sort = 'newest'
        clarified.append('novedades')

    max_price = None
    min_price = None
    max_m = _PRICE_MAX_RE.search(raw)
    if max_m:
        max_price = _parse_decimal(max_m.group(1))
        if max_price is not None:
            clarified.append(f'hasta Bs {max_price}')
    min_m = _PRICE_MIN_RE.search(raw)
    if min_m:
        min_price = _parse_decimal(min_m.group(1))
        if min_price is not None:
            clarified.append(f'desde Bs {min_price}')
    around_m = _PRICE_AROUND_RE.search(raw)
    if around_m and max_price is None and min_price is None:
        mid = _parse_decimal(around_m.group(1))
        if mid is not None:
            min_price = (mid * Decimal('0.7')).quantize(Decimal('0.01'))
            max_price = (mid * Decimal('1.3')).quantize(Decimal('0.01'))
            clarified.append(f'alrededor de Bs {mid}')

    # Free-text search terms (leftover tokens)
    tokens = re.findall(r'[a-z0-9]+', text)
    search_terms: list[str] = []
    for tok in tokens:
        if tok in _STOPWORDS or len(tok) < 3:
            continue
        if tok in _CATEGORY_ALIASES or tok in _COLOR_ALIASES or tok in _GENDER_ALIASES:
            continue
        if tok in _OCCASION_CATEGORIES:
            continue
        if any(tok.startswith(c) and len(tok) <= len(c) + 2 for c in _COLOR_ALIASES):
            continue
        search_terms.append(tok)

    # Occasion keyword boosts as soft search terms (only if no hard category yet
    # would over-constrain — they are OR'd, but skip noisy verb leftovers).
    for occasion in occasions:
        for kw in _OCCASION_KEYWORDS.get(occasion, ()):
            if kw not in _STOPWORDS:
                search_terms.append(kw)

    if wants_gift and not category_slugs:
        category_slugs.extend(('accesorios', 'camisas', 'poleras', 'vestidos'))

    return ChatIntent(
        raw=raw,
        category_slugs=_unique(category_slugs),
        category_keywords=_unique(category_keywords),
        color_names=_unique(color_names),
        brand_keywords=_unique(brand_keywords),
        genders=_unique(genders),
        search_terms=_unique(search_terms)[:6],
        occasions=_unique(occasions),
        min_price=min_price,
        max_price=max_price,
        sort=sort,
        wants_sizes=wants_sizes,
        wants_stock=wants_stock,
        wants_gift=wants_gift,
        wants_outfit=wants_outfit,
        clarified=_unique(clarified)[:8],
    )


def merge_intents(previous: ChatIntent | None, current: ChatIntent) -> ChatIntent:
    """Carry forward filters when the user refines (e.g. 'más barato' after 'negro')."""
    if previous is None:
        return current

    # Pure refinement: sort/price/stock/size without new category/color/gender.
    has_new_structure = bool(
        current.category_slugs
        or current.color_names
        or current.genders
        or current.brand_keywords
        or current.occasions
        or current.search_terms
    )
    is_refinement = (
        not has_new_structure
        and (
            current.sort != 'relevance'
            or current.min_price is not None
            or current.max_price is not None
            or current.wants_sizes
            or current.wants_stock
        )
    )

    if is_refinement:
        return replace(
            previous,
            raw=current.raw,
            sort=current.sort if current.sort != 'relevance' else previous.sort,
            min_price=current.min_price if current.min_price is not None else previous.min_price,
            max_price=current.max_price if current.max_price is not None else previous.max_price,
            wants_sizes=current.wants_sizes or previous.wants_sizes,
            wants_stock=current.wants_stock or previous.wants_stock,
            clarified=_unique(previous.clarified + current.clarified)[:8],
        )

    # Inherit omitted filters so "ahora en negro" keeps prior category, etc.
    return replace(
        current,
        category_slugs=current.category_slugs or previous.category_slugs,
        color_names=current.color_names or previous.color_names,
        genders=current.genders or previous.genders,
        brand_keywords=current.brand_keywords or previous.brand_keywords,
        occasions=current.occasions or previous.occasions,
        clarified=_unique(previous.clarified + current.clarified)[:8],
    )
