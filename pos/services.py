"""POS business logic for FashionStore."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TypedDict

from django.db.models import Count, Q, Sum
from django.utils import timezone

from catalog.models import ProductVariant
from accounts.services.staff import parse_branch_id, resolve_operating_branch
from core.exceptions import BusinessError
from inventory.services import get_stock_levels
from orders.models import Order, OrderChannel, OrderItem, OrderStatus
from orders.services import PAID_ORDER_STATUSES
from payments.models import Payment, PaymentMethod, PaymentStatus


class PosItemInput(TypedDict):
    variant_id: int
    quantity: int


def get_cashier_branch(*, user, branch_id: int | None = None):
    """Return the branch context for POS operations."""
    return resolve_operating_branch(user=user, branch_id=branch_id)


def variant_to_pos_dict(*, variant: ProductVariant, branch) -> dict:
    """Serialize a variant with branch stock for POS UI."""
    stock = get_stock_levels(branch=branch, variant_id=variant.id)
    return {
        'variant_id': variant.id,
        'product_id': variant.product_id,
        'product_name': variant.product.name,
        'sku': variant.sku,
        'barcode': variant.barcode,
        'size': variant.size.code if variant.size_id else None,
        'color': variant.color.name if variant.color_id else None,
        'unit_price': str(variant.effective_price),
        'stock': stock,
    }


def lookup_variant_by_barcode(*, branch, barcode: str) -> dict | None:
    """Resolve variant by barcode or SKU (exact match)."""
    code = barcode.strip()
    if not code:
        return None

    qs = ProductVariant.objects.select_related('product', 'size', 'color').filter(
        is_active=True,
        product__is_active=True,
    )
    variant = qs.filter(barcode=code).first()
    if variant is None:
        variant = qs.filter(sku=code).first()
    if variant is None:
        return None

    return variant_to_pos_dict(variant=variant, branch=branch)


def search_pos_catalog(*, branch, query: str, limit: int = 20) -> list[dict]:
    """
    Quick POS search by barcode/SKU (exact) or product name (partial).
    """
    text = query.strip()
    if not text:
        return []

    exact = lookup_variant_by_barcode(branch=branch, barcode=text)
    if exact is not None:
        return [exact]

    variants = (
        ProductVariant.objects.select_related('product', 'size', 'color')
        .filter(
            is_active=True,
            product__is_active=True,
        )
        .filter(
            Q(product__name__icontains=text)
            | Q(sku__icontains=text)
            | Q(barcode__icontains=text),
        )
        .order_by('product__name', 'sku')[:limit]
    )
    return [variant_to_pos_dict(variant=variant, branch=branch) for variant in variants]


def quote_pos_sale(*, branch, items: list[PosItemInput]) -> dict:
    """Calculate cart totals without persisting an order."""
    lines: list[dict] = []
    subtotal = Decimal('0')

    for item in items:
        try:
            variant = ProductVariant.objects.select_related('product', 'size', 'color').get(
                pk=item['variant_id'],
                is_active=True,
            )
        except ProductVariant.DoesNotExist as err:
            raise BusinessError(
                code='INVALID_VARIANT',
                message=f"Variante no válida: {item['variant_id']}",
                status_code=400,
            ) from err

        quantity = item['quantity']
        unit_price = variant.effective_price
        line_subtotal = unit_price * quantity
        subtotal += line_subtotal
        stock = get_stock_levels(branch=branch, variant_id=variant.id)

        lines.append({
            **variant_to_pos_dict(variant=variant, branch=branch),
            'quantity': quantity,
            'line_subtotal': str(line_subtotal),
            'available': stock['available'] >= quantity,
        })

    tax_total = Decimal('0')
    grand_total = subtotal + tax_total

    return {
        'items': lines,
        'subtotal': str(subtotal),
        'tax_total': str(tax_total),
        'grand_total': str(grand_total),
        'currency': 'BOB',
    }


def get_daily_pos_summary(*, branch, cashier, day: date | None = None, scope: str = 'cashier') -> dict:
    """Sales summary for POS on a given day."""
    target_day = day or timezone.localdate()

    orders = Order.objects.filter(
        channel=OrderChannel.POS,
        branch=branch,
        status__in=PAID_ORDER_STATUSES,
        paid_at__date=target_day,
    )

    if scope == 'cashier':
        orders = orders.filter(created_by=cashier)

    totals = orders.aggregate(
        order_count=Count('id'),
        total_sales=Sum('grand_total'),
    )
    total_sales = totals['total_sales'] or Decimal('0')

    payment_rows = (
        Payment.objects.filter(
            order__in=orders,
            status=PaymentStatus.SUCCEEDED,
        )
        .values('method')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('method')
    )

    by_method = {
        row['method']: {
            'total': str(row['total'] or Decimal('0')),
            'count': row['count'],
        }
        for row in payment_rows
    }

    return {
        'date': target_day.isoformat(),
        'branch_id': branch.id,
        'branch_code': branch.code,
        'cashier_id': cashier.id,
        'cashier_name': cashier.get_full_name() or cashier.email,
        'order_count': totals['order_count'] or 0,
        'total_sales': str(total_sales),
        'currency': 'BOB',
        'by_payment_method': by_method,
    }
