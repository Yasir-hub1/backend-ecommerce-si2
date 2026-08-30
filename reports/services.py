"""Report generation and analytics."""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from io import StringIO

from django.db.models import Count, F, QuerySet, Sum

from inventory.models import BranchStock
from orders.models import Order, OrderItem, OrderStatus
from reports.models import ReportRequest, ReportStatus
from reports.prompt_interpreter import InterpretedReportSpec, ProductRanking, interpret_prompt
from reservations.models import Reservation, ReservationStatus

EXPORT_REPORT_TYPES = frozenset({'sales', 'inventory', 'reservations'})

PAID_ORDER_STATUSES = [
    OrderStatus.PAID,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.DELIVERED,
]


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _apply_date_filters(
    *,
    orders: QuerySet[Order] | None = None,
    reservations: QuerySet[Reservation] | None = None,
    date_from: date | None,
    date_to: date | None,
) -> tuple[QuerySet[Order] | None, QuerySet[Reservation] | None]:
    if orders is not None:
        if date_from:
            orders = orders.filter(paid_at__date__gte=date_from)
        if date_to:
            orders = orders.filter(paid_at__date__lte=date_to)
    if reservations is not None:
        if date_from:
            reservations = reservations.filter(scheduled_for__date__gte=date_from)
        if date_to:
            reservations = reservations.filter(scheduled_for__date__lte=date_to)
    return orders, reservations


def _orders_queryset(*, branch_id: int | None, date_from: date | None, date_to: date | None) -> QuerySet[Order]:
    orders = Order.objects.filter(status__in=PAID_ORDER_STATUSES)
    if branch_id:
        orders = orders.filter(branch_id=branch_id)
    orders, _ = _apply_date_filters(
        orders=orders,
        reservations=None,
        date_from=date_from,
        date_to=date_to,
    )
    return orders


def _reservations_queryset(
    *,
    branch_id: int | None,
    date_from: date | None,
    date_to: date | None,
) -> QuerySet[Reservation]:
    reservations = Reservation.objects.exclude(status=ReservationStatus.CANCELLED)
    if branch_id:
        reservations = reservations.filter(branch_id=branch_id)
    _, reservations = _apply_date_filters(
        orders=None,
        reservations=reservations,
        date_from=date_from,
        date_to=date_to,
    )
    return reservations


def build_report_summary(*, branch_id: int | None, date_from: str | None, date_to: str | None) -> dict:
    start = _parse_date(date_from)
    end = _parse_date(date_to)
    orders = _orders_queryset(branch_id=branch_id, date_from=start, date_to=end)
    reservations = _reservations_queryset(branch_id=branch_id, date_from=start, date_to=end)

    total_sales = orders.aggregate(total=Sum('grand_total'))['total'] or Decimal('0')
    order_count = orders.count()
    reservation_count = reservations.count()

    completed_reservations = reservations.filter(status=ReservationStatus.COMPLETED).count()
    conversion_rate = (
        round(completed_reservations / reservation_count * 100, 1)
        if reservation_count
        else 0.0
    )

    stock_qs = BranchStock.objects.all()
    if branch_id:
        stock_qs = stock_qs.filter(branch_id=branch_id)
    low_stock_count = stock_qs.filter(on_hand__lte=F('min_threshold')).count()

    top_rows = (
        OrderItem.objects.filter(order__in=orders)
        .values('variant__product__name')
        .annotate(units_sold=Sum('quantity'), revenue=Sum(F('quantity') * F('unit_price')))
        .order_by('-units_sold')[:5]
    )
    top_products = [
        {
            'product_name': row['variant__product__name'],
            'units_sold': row['units_sold'] or 0,
            'revenue': str(row['revenue'] or Decimal('0')),
        }
        for row in top_rows
    ]

    return {
        'total_sales': str(total_sales),
        'order_count': order_count,
        'reservation_count': reservation_count,
        'conversion_rate': conversion_rate,
        'low_stock_count': low_stock_count,
        'top_products': top_products,
    }


def _fetch_ranked_products(
    *,
    orders: QuerySet[Order],
    limit: int,
    ranking: ProductRanking,
) -> list[dict]:
    rows = (
        OrderItem.objects.filter(order__in=orders)
        .values('variant__product__name')
        .annotate(units_sold=Sum('quantity'), revenue=Sum(F('quantity') * F('unit_price')))
    )
    if ranking == 'worst':
        rows = rows.order_by('units_sold', 'revenue')
    else:
        rows = rows.order_by('-units_sold', '-revenue')
    return [
        {
            'product_name': row['variant__product__name'],
            'units_sold': row['units_sold'] or 0,
            'revenue': str(row['revenue'] or Decimal('0')),
        }
        for row in rows[:limit]
    ]


def _fetch_sales_orders(*, orders: QuerySet[Order], limit: int) -> list[dict]:
    return [
        {
            'code': order.code,
            'branch_code': order.branch.code,
            'channel': order.channel,
            'status': order.status,
            'grand_total': str(order.grand_total),
            'paid_at': order.paid_at.isoformat() if order.paid_at else '',
        }
        for order in orders.select_related('branch').order_by('-paid_at')[:limit]
    ]


def _fetch_low_stock(*, branch_id: int | None, limit: int = 10) -> list[dict]:
    stock_qs = BranchStock.objects.select_related('branch', 'variant__product').filter(
        on_hand__lte=F('min_threshold'),
    )
    if branch_id:
        stock_qs = stock_qs.filter(branch_id=branch_id)
    return [
        {
            'branch_code': row.branch.code,
            'sku': row.variant.sku,
            'product_name': row.variant.product.name,
            'on_hand': row.on_hand,
            'min_threshold': row.min_threshold,
        }
        for row in stock_qs.order_by('on_hand')[:limit]
    ]


def _fetch_inventory_totals(*, branch_id: int | None) -> dict:
    stock_qs = BranchStock.objects.all()
    if branch_id:
        stock_qs = stock_qs.filter(branch_id=branch_id)
    return {
        'sku_count': stock_qs.count(),
        'units_on_hand': stock_qs.aggregate(total=Sum('on_hand'))['total'] or 0,
        'units_reserved': stock_qs.aggregate(total=Sum('reserved'))['total'] or 0,
    }


def build_report_payload(spec: InterpretedReportSpec) -> dict:
    orders = _orders_queryset(
        branch_id=spec.branch_id,
        date_from=spec.date_from,
        date_to=spec.date_to,
    )
    reservations = _reservations_queryset(
        branch_id=spec.branch_id,
        date_from=spec.date_from,
        date_to=spec.date_to,
    )

    payload: dict = {
        'interpreted': spec.to_dict(),
    }

    if spec.include_sales:
        total_sales = orders.aggregate(total=Sum('grand_total'))['total'] or Decimal('0')
        payload['sales'] = {
            'total_sales': str(total_sales),
            'order_count': orders.count(),
        }
        if spec.include_sales_detail and spec.sales_detail_limit > 0:
            payload['sales']['orders'] = _fetch_sales_orders(
                orders=orders,
                limit=spec.sales_detail_limit,
            )

    if spec.include_top_products:
        if not spec.include_sales:
            total_sales = orders.aggregate(total=Sum('grand_total'))['total'] or Decimal('0')
            payload['sales_context'] = {
                'total_sales': str(total_sales),
                'order_count': orders.count(),
            }
        payload['product_ranking'] = spec.product_ranking
        payload['top_products'] = _fetch_ranked_products(
            orders=orders,
            limit=spec.top_limit,
            ranking=spec.product_ranking,
        )

    if spec.include_reservations:
        reservation_count = reservations.count()
        completed = reservations.filter(status=ReservationStatus.COMPLETED).count()
        payload['reservations'] = {
            'count': reservation_count,
            'completed': completed,
            'conversion_rate': round(completed / reservation_count * 100, 1) if reservation_count else 0.0,
            'by_status': list(
                reservations.values('status').annotate(total=Count('id')).order_by('-total'),
            ),
        }

    if spec.include_inventory or spec.include_low_stock:
        payload['inventory'] = _fetch_inventory_totals(branch_id=spec.branch_id)
        if spec.include_low_stock:
            payload['low_stock_items'] = _fetch_low_stock(branch_id=spec.branch_id)

    return payload


def render_generative_report(*, prompt: str, spec: InterpretedReportSpec, payload: dict) -> str:
    lines = [
        f'Consulta: {prompt.strip()}',
        f'Periodo: {spec.period_label}',
        f'Ámbito: {spec.scope_label}',
        '',
    ]

    if spec.include_sales and 'sales' in payload:
        sales = payload['sales']
        lines.append(
            f"Ventas: {sales['total_sales']} BOB en {sales['order_count']} órdenes.",
        )
        orders = sales.get('orders') or []
        if orders:
            lines.append('')
            lines.append('Detalle de ventas:')
            for order in orders:
                paid = order['paid_at'][:10] if order['paid_at'] else 'sin fecha'
                lines.append(
                    f"  • {order['code']} | {order['branch_code']} | {order['channel']} | "
                    f"{order['grand_total']} BOB | {paid}",
                )
            if sales['order_count'] > len(orders):
                lines.append(
                    f"  … y {sales['order_count'] - len(orders)} órdenes más "
                    f"(usa export CSV para el listado completo).",
                )

    if spec.include_top_products and payload.get('top_products'):
        ranking: ProductRanking = payload.get('product_ranking', spec.product_ranking)
        if not spec.include_sales and payload.get('sales_context'):
            ctx = payload['sales_context']
            lines.append(
                f"Análisis sobre {ctx['order_count']} órdenes "
                f"({ctx['total_sales']} BOB en el periodo).",
            )

        lines.append('')
        if ranking == 'worst':
            lines.append('Productos con menor venta:')
        else:
            lines.append('Ranking de productos:')

        for index, product in enumerate(payload['top_products'], start=1):
            lines.append(
                f"  {index}. {product['product_name']} — "
                f"{product['units_sold']} u., {product['revenue']} BOB",
            )

        highlighted = payload['top_products'][0]
        if ranking == 'worst':
            lines.append(
                f"\nProducto menos vendido del periodo: {highlighted['product_name']} "
                f"({highlighted['units_sold']} unidades, {highlighted['revenue']} BOB).",
            )
        else:
            lines.append(
                f"\nMejor producto del periodo: {highlighted['product_name']} "
                f"({highlighted['units_sold']} unidades, {highlighted['revenue']} BOB).",
            )

    if spec.include_reservations and 'reservations' in payload:
        res = payload['reservations']
        lines.append('')
        lines.append(
            f"Reservas: {res['count']} totales, {res['completed']} completadas "
            f"(conversión {res['conversion_rate']}%).",
        )
        if res.get('by_status'):
            status_bits = ', '.join(
                f"{row['status']}: {row['total']}" for row in res['by_status'][:4]
            )
            lines.append(f"  Por estado: {status_bits}.")

    if spec.include_inventory and 'inventory' in payload:
        inv = payload['inventory']
        lines.append('')
        lines.append(
            f"Inventario: {inv['sku_count']} SKUs, {inv['units_on_hand']} unidades en piso "
            f"({inv['units_reserved']} reservadas).",
        )

    if spec.include_low_stock:
        low_stock = payload.get('low_stock_items') or []
        lines.append('')
        if low_stock:
            lines.append('Alertas de stock bajo:')
            for item in low_stock:
                lines.append(
                    f"  • {item['branch_code']} | {item['product_name']} ({item['sku']}) — "
                    f"{item['on_hand']} u. (mín. {item['min_threshold']})",
                )
        else:
            lines.append('Alertas de stock bajo: ninguna en el ámbito seleccionado.')

    if len(lines) <= 4:
        lines.append('No encontré datos para esa consulta. Prueba mencionar ventas, inventario o reservas.')

    return '\n'.join(lines)


def generate_report(*, user, prompt: str, report_type: str | None, branch_id: int | None) -> ReportRequest:
    spec = interpret_prompt(prompt=prompt, branch_id=branch_id)
    payload = build_report_payload(spec)
    result_text = render_generative_report(prompt=prompt, spec=spec, payload=payload)

    interpreted = spec.to_dict()
    interpreted['report_type'] = report_type or 'GENERATIVE'

    return ReportRequest.objects.create(
        user=user,
        prompt_text=prompt,
        interpreted_spec=interpreted,
        result={'text': result_text, 'data': payload},
        status=ReportStatus.COMPLETED,
    )


def export_report_csv(*, report_type: str, branch_id: int | None, date_from: str | None, date_to: str | None) -> str:
    if report_type not in EXPORT_REPORT_TYPES:
        raise ValueError(f'Unsupported report type: {report_type}')

    buffer = StringIO()
    writer = csv.writer(buffer)
    start, end = _parse_date(date_from), _parse_date(date_to)

    if report_type == 'sales':
        writer.writerow(['code', 'branch', 'channel', 'status', 'grand_total', 'paid_at'])
        orders = _orders_queryset(branch_id=branch_id, date_from=start, date_to=end)
        for order in orders.select_related('branch').order_by('-paid_at'):
            writer.writerow([
                order.code,
                order.branch.code,
                order.channel,
                order.status,
                order.grand_total,
                order.paid_at.isoformat() if order.paid_at else '',
            ])

    elif report_type == 'inventory':
        writer.writerow(['branch', 'sku', 'on_hand', 'reserved', 'available', 'min_threshold'])
        stock_qs = BranchStock.objects.select_related('branch', 'variant').all()
        if branch_id:
            stock_qs = stock_qs.filter(branch_id=branch_id)
        for row in stock_qs:
            writer.writerow([
                row.branch.code,
                row.variant.sku,
                row.on_hand,
                row.reserved,
                row.on_hand - row.reserved,
                row.min_threshold,
            ])

    elif report_type == 'reservations':
        writer.writerow(['code', 'branch', 'status', 'scheduled_for', 'customer'])
        reservations = _reservations_queryset(branch_id=branch_id, date_from=start, date_to=end)
        for reservation in reservations.select_related('branch', 'customer__user').order_by('-scheduled_for'):
            writer.writerow([
                reservation.code,
                reservation.branch.code,
                reservation.status,
                reservation.scheduled_for.isoformat(),
                reservation.customer.user.email if reservation.customer else '',
            ])

    return buffer.getvalue()
