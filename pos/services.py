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


def customer_to_pos_dict(*, profile) -> dict:
    """Serialize a customer for POS search / selection."""
    user = profile.user
    return {
        'id': user.id,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': user.get_full_name(),
        'email': profile.receipt_email,
        'phone': user.phone or '',
        'document_type': profile.document_type or '',
        'document_number': profile.document_number or '',
        'document_label': profile.document_label,
    }


def search_pos_customers(*, query: str, limit: int = 20) -> list[dict]:
    """Search customers by name, email, phone or document number."""
    from accounts.models import CustomerProfile, Role

    text = query.strip()
    if not text:
        return []

    qs = (
        CustomerProfile.objects.select_related('user')
        .filter(user__role=Role.CUSTOMER, user__is_active=True)
        .filter(
            Q(user__first_name__icontains=text)
            | Q(user__last_name__icontains=text)
            | Q(user__email__icontains=text)
            | Q(user__phone__icontains=text)
            | Q(document_number__icontains=text),
        )
        .order_by('user__last_name', 'user__first_name')[:limit]
    )
    return [customer_to_pos_dict(profile=p) for p in qs]


def create_pos_walk_in_customer(
    *,
    first_name: str,
    last_name: str,
    document_type: str,
    document_number: str,
    email: str | None = None,
    phone: str | None = None,
):
    """
    Quick-create a customer from the POS register (walk-in with CI/NIT).

    Uses a synthetic @pos.local email when none is provided so the account
    is unique without forcing the cashier to invent an email.
    """
    import secrets

    from accounts.models import CustomerProfile, DocumentType, Role, User

    doc_type = (document_type or '').strip().upper()
    doc_number = (document_number or '').strip()
    if doc_type not in {c for c, _ in DocumentType.CHOICES}:
        raise BusinessError(
            code='INVALID_DOCUMENT_TYPE',
            message='Tipo de documento inválido',
            status_code=400,
        )
    if not doc_number:
        raise BusinessError(
            code='DOCUMENT_REQUIRED',
            message='El número de documento es obligatorio',
            status_code=400,
        )

    existing = (
        CustomerProfile.objects.select_related('user')
        .filter(document_type=doc_type, document_number__iexact=doc_number)
        .first()
    )
    if existing is not None:
        # Update name/phone if the same document returns to the counter.
        user = existing.user
        changed = False
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if last_name and user.last_name != last_name:
            user.last_name = last_name
            changed = True
        if phone and user.phone != phone:
            user.phone = phone
            changed = True
        if changed:
            user.save(update_fields=['first_name', 'last_name', 'phone', 'updated_at'])
        return existing

    clean_email = (email or '').strip().lower()
    if clean_email:
        if User.objects.filter(email__iexact=clean_email).exists():
            raise BusinessError(
                code='EMAIL_TAKEN',
                message='Ya existe un usuario con ese correo',
                status_code=400,
            )
    else:
        slug = ''.join(ch for ch in doc_number.lower() if ch.isalnum()) or 'cliente'
        clean_email = f'pos+{doc_type.lower()}.{slug}@pos.local'
        # Collision guard for repeated synthetic emails
        if User.objects.filter(email__iexact=clean_email).exists():
            clean_email = f'pos+{doc_type.lower()}.{slug}.{User.objects.count()}@pos.local'

    user = User.objects.create_user(
        email=clean_email,
        password=secrets.token_urlsafe(24),
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        phone=(phone or '').strip() or None,
        role=Role.CUSTOMER,
    )
    user.set_unusable_password()
    user.save(update_fields=['password'])

    profile = CustomerProfile.objects.create(
        user=user,
        document_type=doc_type,
        document_number=doc_number,
    )
    return profile
