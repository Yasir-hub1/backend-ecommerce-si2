"""Rule-based natural language interpreter for generative report prompts."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Literal

ProductRanking = Literal['best', 'worst']


def normalize_text(text: str) -> str:
    lowered = text.lower().strip()
    decomposed = unicodedata.normalize('NFKD', lowered)
    return ''.join(ch for ch in decomposed if not unicodedata.combining(ch))


@dataclass(frozen=True)
class InterpretedReportSpec:
    include_sales: bool
    include_sales_detail: bool
    include_top_products: bool
    product_ranking: ProductRanking
    include_reservations: bool
    include_inventory: bool
    include_low_stock: bool
    date_from: date | None
    date_to: date | None
    branch_id: int | None
    top_limit: int
    sales_detail_limit: int
    period_label: str
    scope_label: str

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload['date_from'] = self.date_from.isoformat() if self.date_from else None
        payload['date_to'] = self.date_to.isoformat() if self.date_to else None
        return payload


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _parse_date_range(text: str, *, today: date) -> tuple[date | None, date | None, str]:
    if _contains_any(text, ('hoy', 'dia de hoy')):
        return today, today, 'Hoy'

    if 'ayer' in text:
        day = today - timedelta(days=1)
        return day, day, 'Ayer'

    if _contains_any(text, ('ultima semana', 'semana pasada', 'ultimos 7 dias', 'ultimos siete dias')):
        start = today - timedelta(days=7)
        return start, today, 'Últimos 7 días'

    if _contains_any(text, ('este mes', 'mes actual', 'mes en curso')):
        start = today.replace(day=1)
        return start, today, 'Mes en curso'

    if _contains_any(text, ('ultimo mes', 'mes pasado', 'ultimos 30 dias', 'ultimos treinta dias')):
        first_this_month = today.replace(day=1)
        end = first_this_month - timedelta(days=1)
        start = end.replace(day=1)
        return start, end, 'Mes anterior'

    iso_match = re.search(r'(\d{4}-\d{2}-\d{2})\s*(?:a|hasta|-)\s*(\d{4}-\d{2}-\d{2})', text)
    if iso_match:
        start = date.fromisoformat(iso_match.group(1))
        end = date.fromisoformat(iso_match.group(2))
        return start, end, f'{start.isoformat()} → {end.isoformat()}'

    return None, None, 'Histórico completo'


def _resolve_branch_id(text: str, explicit_branch_id: int | None) -> tuple[int | None, str]:
    if explicit_branch_id is not None:
        from branches.models import Branch

        branch = Branch.objects.filter(pk=explicit_branch_id).first()
        if branch:
            return explicit_branch_id, f'Sucursal {branch.name} ({branch.code})'
        return explicit_branch_id, f'Sucursal #{explicit_branch_id}'

    code_match = re.search(r'\b([a-z]{2,}-\d{2})\b', text)
    branch_hint = _contains_any(text, ('sucursal', 'tienda', 'branch', 'local')) or bool(code_match)
    if not branch_hint:
        return None, 'Todas las sucursales'

    from branches.models import Branch

    if code_match:
        branch = Branch.objects.filter(code__iexact=code_match.group(1)).first()
        if branch:
            return branch.id, f'Sucursal {branch.name} ({branch.code})'

    for branch in Branch.objects.all().order_by('-is_active', 'name'):
        tokens = normalize_text(f'{branch.name} {branch.code}')
        if branch.code.lower() in text or tokens in text or any(
            part in text for part in tokens.split() if len(part) >= 4
        ):
            return branch.id, f'Sucursal {branch.name} ({branch.code})'

    return None, 'Todas las sucursales (sin coincidencia específica)'


def interpret_prompt(*, prompt: str, branch_id: int | None = None, today: date | None = None) -> InterpretedReportSpec:
    text = normalize_text(prompt)
    today = today or date.today()

    wants_sales = _matches_any(
        text,
        (
            r'\bventas?\b',
            r'\bvendidos?\b',
            r'\bingresos?\b',
            r'\bfactur',
            r'\bordenes?\b',
            r'\bpedidos?\b',
            r'\btickets?\b',
            r'\bcobr',
        ),
    )
    wants_sales_detail = _contains_any(
        text,
        (
            'todas las ventas',
            'lista de ventas',
            'listado de ventas',
            'detalle de ventas',
            'desglose',
            'cada venta',
            'ventas incluyendo',
            'incluyendo que producto',
        ),
    ) or ('todas' in text and 'venta' in text)

    wants_worst_products = _matches_any(
        text,
        (
            r'\bmenos vend',
            r'\bvende menos\b',
            r'\bse vende menos\b',
            r'\bpeor producto\b',
            r'\bpeor rendimiento\b',
            r'\bmenor venta\b',
            r'\bproductos? con menos ventas\b',
            r'\bultimo[s]? en ventas\b',
            r'\bbottom\b',
        ),
    )
    wants_best_products = (
        _contains_any(
            text,
            ('mejor producto', 'mas vendido', 'más vendido', 'top producto', 'producto estrella'),
        )
        or ('mejor' in text and 'producto' in text and not wants_worst_products)
    )
    wants_product_ranking = wants_best_products or wants_worst_products or _contains_any(
        text,
        ('ranking', 'top producto', 'cual producto', 'cuál producto', 'que producto', 'qué producto'),
    )
    wants_top = wants_product_ranking
    product_ranking: ProductRanking = 'worst' if wants_worst_products and not wants_best_products else 'best'
    wants_reservations = _contains_any(
        text,
        ('reserva', 'probador', 'cita', 'conversion de reserva', 'conversión de reserva'),
    )
    wants_inventory = _matches_any(text, (r'\binventarios?\b', r'\bexistencias?\b', r'\bstock\b'))
    wants_low_stock = _contains_any(
        text,
        ('stock bajo', 'reposicion', 'reposición', 'alerta de stock', 'minimo', 'mínimo'),
    )

    specific_topics = any(
        (wants_sales, wants_top, wants_reservations, wants_inventory, wants_low_stock),
    )

    if wants_product_ranking and not wants_sales:
        wants_sales = False

    if not specific_topics:
        wants_sales = wants_reservations = wants_inventory = True
        wants_top = True
        wants_low_stock = True
    elif wants_sales and not (wants_reservations or wants_inventory or wants_low_stock):
        wants_low_stock = False

    if wants_sales and ('todas' in text or 'detalle' in text or 'listado' in text):
        wants_sales_detail = True

    date_from, date_to, period_label = _parse_date_range(text, today=today)
    resolved_branch_id, scope_label = _resolve_branch_id(text, branch_id)

    top_limit = 10 if _contains_any(text, ('top 10', 'diez productos', '10 productos')) else 5
    if _contains_any(text, ('top 3', 'tres productos', '3 productos')):
        top_limit = 3

    sales_detail_limit = 50 if wants_sales_detail else 0
    if _contains_any(text, ('ultimas 10', 'últimas 10', '10 ventas')):
        sales_detail_limit = 10
    elif _contains_any(text, ('ultimas 20', 'últimas 20', '20 ventas')):
        sales_detail_limit = 20

    return InterpretedReportSpec(
        include_sales=wants_sales,
        include_sales_detail=wants_sales_detail,
        include_top_products=wants_top,
        product_ranking=product_ranking,
        include_reservations=wants_reservations,
        include_inventory=wants_inventory,
        include_low_stock=wants_low_stock or wants_inventory,
        date_from=date_from,
        date_to=date_to,
        branch_id=resolved_branch_id,
        top_limit=top_limit,
        sales_detail_limit=sales_detail_limit,
        period_label=period_label,
        scope_label=scope_label,
    )
