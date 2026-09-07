"""
Order services for FashionStore.

Handles cart checkout, order payment, and refunds.
"""
from typing import Optional, List, Dict
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessError
from orders.models import Cart, Order, OrderItem, OrderStatus, OrderChannel
from reservations.models import Reservation, ReservationStatus, ItemStatus
from inventory.services import apply_movements, check_availability, get_stock_levels
from inventory.models import MovementType, ReferenceType

PAID_ORDER_STATUSES = [
    OrderStatus.PAID,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.DELIVERED,
]


@transaction.atomic
def checkout_from_cart(
    *,
    customer,
    branch,
    channel: str,
    promotion_code: Optional[str] = None,
) -> Order:
    """
    Convert cart to order.

    Does NOT deduct stock yet - stock is deducted when payment is confirmed.
    This prevents holding inventory for abandoned carts.

    Args:
        customer: CustomerProfile instance
        branch: Branch for pickup/delivery
        channel: OrderChannel (WEB, MOBILE, POS)
        promotion_code: Optional promotion code

    Returns:
        Created Order instance in PENDING_PAYMENT status

    Raises:
        BusinessError: If cart is empty or validation fails
    """
    try:
        cart = Cart.objects.select_related('customer').get(customer=customer)
    except Cart.DoesNotExist:
        raise BusinessError(
            code='EMPTY_CART',
            message='El carrito está vacío',
            status_code=400,
        )

    cart_items = cart.items.select_related('variant__product').all()

    if not cart_items:
        raise BusinessError(
            code='EMPTY_CART',
            message='El carrito está vacío',
            status_code=400,
        )

    # Revalidate stock availability (prices will be frozen at current values)
    unavailable = []
    for item in cart_items:
        if not check_availability(
            branch=branch,
            variant_id=item.variant_id,
            quantity=item.quantity
        ):
            unavailable.append({
                'variant_id': item.variant_id,
                'product_name': item.variant.product.name,
                'quantity': item.quantity,
                'available_qty': get_stock_levels(branch=branch, variant_id=item.variant_id)['available'],
            })

    if unavailable:
        names = ', '.join(entry['product_name'] for entry in unavailable)
        raise BusinessError(
            code='INSUFFICIENT_STOCK',
            message=f'Sin stock suficiente en esta sucursal: {names}',
            status_code=409,
            details={'unavailable_items': unavailable}
        )

    # Calculate totals
    subtotal = Decimal('0')
    order_items_data = []

    for item in cart_items:
        unit_price = item.variant.effective_price
        line_subtotal = unit_price * item.quantity

        order_items_data.append({
            'variant': item.variant,
            'quantity': item.quantity,
            'unit_price': unit_price,
            'discount_amount': Decimal('0'),  # TODO: Apply promotion
        })

        subtotal += line_subtotal

    # TODO: Apply promotion if code provided
    discount_total = Decimal('0')

    # TODO: Calculate tax (Bolivia: 13% IT)
    tax_total = Decimal('0')  # For now, prices include tax

    grand_total = subtotal - discount_total + tax_total

    # Create order
    order = Order.objects.create(
        customer=customer,
        branch=branch,
        channel=channel,
        status=OrderStatus.PENDING_PAYMENT,
        subtotal=subtotal,
        discount_total=discount_total,
        tax_total=tax_total,
        grand_total=grand_total,
        currency='BOB',
    )

    # Create order items
    order_items = [
        OrderItem(
            order=order,
            variant=item_data['variant'],
            quantity=item_data['quantity'],
            unit_price=item_data['unit_price'],
            discount_amount=item_data['discount_amount'],
        )
        for item_data in order_items_data
    ]
    OrderItem.objects.bulk_create(order_items)

    # Clear cart
    cart_items.delete()

    return order


@transaction.atomic
def mark_order_as_paid(
    *,
    order_id: int,
    payment,
) -> Order:
    """
    Mark order as paid and deduct stock.

    This is called from the payment webhook/confirmation.

    Args:
        order_id: Order ID
        payment: Payment instance that succeeded

    Returns:
        Updated Order instance

    Raises:
        BusinessError: If insufficient stock at payment time
    """
    order = Order.objects.select_for_update().get(pk=order_id)

    if order.status != OrderStatus.PENDING_PAYMENT:
        raise BusinessError(
            code='INVALID_ORDER_STATUS',
            message=f'La orden no está pendiente de pago. Estado: {order.get_status_display()}',
            status_code=400,
            details={'order_code': order.code, 'current_status': order.status}
        )

    # Revalidate stock at payment time
    # This is critical: cart might be abandoned for hours before payment
    order_items = order.items.select_related('variant').all()

    # Determine movement type based on whether order came from reservation
    if order.reservation_id:
        movement_type = MovementType.OUT_SALE_RESERVED
        # Update reservation items status
        order.reservation.items.filter(
            variant__in=[item.variant for item in order_items]
        ).update(item_status=ItemStatus.PURCHASED)

        # Items not purchased return to floor
        order.reservation.items.exclude(
            variant__in=[item.variant for item in order_items]
        ).update(item_status=ItemStatus.RETURNED_TO_FLOOR)

        order.reservation.status = ReservationStatus.COMPLETED
        order.reservation.save(update_fields=['status', 'updated_at'])
    else:
        movement_type = MovementType.OUT_SALE

    # Prepare inventory movements
    lines = [(item.variant_id, item.quantity) for item in order_items]

    try:
        apply_movements(
            branch=order.branch,
            lines=lines,
            movement_type=movement_type,
            reference_type=ReferenceType.ORDER,
            reference_id=order.id,
            user=order.customer.user if order.customer else None,
            note=f"Venta {order.code}"
        )
    except BusinessError as e:
        # Stock validation failed at payment time
        # Order should be cancelled and payment refunded
        order.status = OrderStatus.CANCELLED
        order.save(update_fields=['status', 'updated_at'])

        # Trigger automatic refund
        from payments.services import process_stripe_refund
        if payment.provider == 'STRIPE':
            try:
                process_stripe_refund(
                    payment_id=payment.id,
                    reason="Insufficient stock at payment time"
                )
            except Exception as refund_error:
                # Log refund error but don't fail the transaction
                # Manual refund may be needed
                print(f"Auto-refund failed for payment {payment.id}: {refund_error}")

        raise BusinessError(
            code='PAYMENT_FAILED_NO_STOCK',
            message='No hay stock suficiente. El pago será reembolsado.',
            status_code=409,
            details=e.details
        )

    # Update order status
    order.status = OrderStatus.PAID
    order.paid_at = timezone.now()
    order.save(update_fields=['status', 'paid_at', 'updated_at'])

    # Generate receipt (handled in webhook, but can also be called directly for POS)
    # Note: Webhook handler already generates receipt, but this is here for POS flow
    # from payments.services import generate_receipt
    # generate_receipt(order_id=order.id)

    # TODO: Send confirmation email/notification
    # from notifications.services import send_order_confirmation
    # send_order_confirmation(order_id=order.id)

    return order


@transaction.atomic
def cancel_order(
    *,
    order_id: int,
    reason: str = "",
) -> Order:
    """
    Cancel an order.

    Can only cancel orders that haven't been paid yet.

    Args:
        order_id: Order ID
        reason: Cancellation reason

    Returns:
        Updated Order instance
    """
    order = Order.objects.select_for_update().get(pk=order_id)

    if order.status != OrderStatus.PENDING_PAYMENT:
        raise BusinessError(
            code='CANNOT_CANCEL',
            message='Solo se pueden cancelar órdenes pendientes de pago',
            status_code=400,
            details={'order_code': order.code, 'current_status': order.status}
        )

    order.status = OrderStatus.CANCELLED
    order.save(update_fields=['status', 'updated_at'])

    return order


@transaction.atomic
def refund_order(
    *,
    order_id: int,
    reason: str,
) -> Order:
    """
    Refund a paid order and return items to stock.

    Args:
        order_id: Order ID
        reason: Refund reason

    Returns:
        Updated Order instance

    Raises:
        BusinessError: If order cannot be refunded
    """
    order = Order.objects.select_for_update().get(pk=order_id)

    if order.status not in [OrderStatus.PAID, OrderStatus.PREPARING, OrderStatus.READY]:
        raise BusinessError(
            code='CANNOT_REFUND',
            message='Solo se pueden reembolsar órdenes pagadas que no han sido entregadas',
            status_code=400,
            details={'order_code': order.code, 'current_status': order.status}
        )

    # Return items to stock
    order_items = order.items.select_related('variant').all()
    lines = [(item.variant_id, item.quantity) for item in order_items]

    apply_movements(
        branch=order.branch,
        lines=lines,
        movement_type=MovementType.RETURN_IN,
        reference_type=ReferenceType.ORDER,
        reference_id=order.id,
        note=f"Devolución de orden {order.code}: {reason}"
    )

    # Update order status
    order.status = OrderStatus.REFUNDED
    order.save(update_fields=['status', 'updated_at'])

    # Process Stripe refund for all successful payments
    from payments.services import process_stripe_refund
    from payments.models import PaymentStatus, PaymentProvider

    for payment in order.payments.filter(status=PaymentStatus.SUCCEEDED):
        if payment.provider == PaymentProvider.STRIPE:
            try:
                process_stripe_refund(payment_id=payment.id, reason=reason)
            except Exception as e:
                # Log error but continue with other payments
                print(f"Failed to refund payment {payment.id}: {e}")

    return order


def create_pos_sale(
    *,
    branch,
    cashier,
    items: List[Dict],  # [{'variant_id': 1, 'quantity': 2}, ...]
    payments: List[Dict],  # [{'method': 'CASH', 'amount': 100}, ...]
    customer=None,
    reservation_id: Optional[int] = None,
) -> Order:
    """
    Create a POS sale (already paid).

    This is for in-store sales at the point of sale.

    Args:
        branch: Branch where sale occurs
        cashier: User (cashier) creating the sale
        items: List of items to sell
        payments: List of payment methods and amounts
        customer: Optional customer (for loyalty, etc.)
        reservation_id: Optional reservation this sale completes

    Returns:
        Created Order instance in PAID status

    Raises:
        BusinessError: If validation fails
    """
    # This is a higher-level function that combines checkout + payment
    # For POS, we create the order already paid

    # Calculate totals
    from catalog.models import ProductVariant

    subtotal = Decimal('0')
    order_items_data = []

    for item in items:
        variant = ProductVariant.objects.get(pk=item['variant_id'])
        unit_price = variant.effective_price
        quantity = item['quantity']

        line_subtotal = unit_price * quantity
        subtotal += line_subtotal

        order_items_data.append({
            'variant': variant,
            'quantity': quantity,
            'unit_price': unit_price,
            'discount_amount': Decimal('0'),
        })

    # Validate total payment
    total_payment = sum(Decimal(str(p['amount'])) for p in payments)

    discount_total = Decimal('0')
    tax_total = Decimal('0')
    grand_total = subtotal - discount_total + tax_total

    if total_payment < grand_total:
        raise BusinessError(
            code='INSUFFICIENT_PAYMENT',
            message=f'Pago insuficiente. Total: {grand_total}, Recibido: {total_payment}',
            status_code=400,
        )

    from payments.services import validate_pos_payment

    payment_rows = [dict(payment) for payment in payments]
    payment_summary = validate_pos_payment(total_due=grand_total, payments=payment_rows)

    # Get reservation if provided
    reservation = None
    reservation_items_map: dict = {}
    if reservation_id:
        from reservations.models import Reservation, ReservationStatus

        reservation = Reservation.objects.select_related('branch').get(pk=reservation_id)

        if reservation.branch_id != branch.id:
            raise BusinessError(
                code='BRANCH_MISMATCH',
                message='La reserva pertenece a otra sucursal',
                status_code=400,
            )

        if reservation.status not in (
            ReservationStatus.IN_FITTING,
            ReservationStatus.READY,
        ):
            raise BusinessError(
                code='INVALID_RESERVATION_STATUS',
                message='La reserva debe estar lista o en probador para cobrar',
                status_code=409,
                details={'current_status': reservation.status},
            )

        reservation_items_map = {
            item.variant_id: item for item in reservation.items.select_related('variant')
        }

        for item in items:
            reserved_item = reservation_items_map.get(item['variant_id'])
            if reserved_item is None:
                continue
            if item['quantity'] > reserved_item.quantity:
                raise BusinessError(
                    code='INVALID_RESERVATION_QUANTITY',
                    message=(
                        f"Cantidad vendida mayor a la reservada para "
                        f"{reserved_item.variant.sku}"
                    ),
                    status_code=400,
                )

    # Re-validate stock (reservation lines use reserved stock, not generic available)
    for item in items:
        variant_id = item['variant_id']
        quantity = item['quantity']
        if reservation and variant_id in reservation_items_map:
            continue
        if not check_availability(branch=branch, variant_id=variant_id, quantity=quantity):
            variant = ProductVariant.objects.get(pk=variant_id)
            raise BusinessError(
                code='INSUFFICIENT_STOCK',
                message=f'Stock insuficiente para {variant.product.name}',
                status_code=409,
            )

    # Create order with transaction
    with transaction.atomic():
        order = Order.objects.create(
            customer=customer,
            branch=branch,
            channel=OrderChannel.POS,
            reservation=reservation,
            status=OrderStatus.PAID,  # Already paid
            subtotal=subtotal,
            discount_total=discount_total,
            tax_total=tax_total,
            grand_total=grand_total,
            currency='BOB',
            created_by=cashier,
            paid_at=timezone.now(),
        )

        # Create order items
        order_items = [
            OrderItem(
                order=order,
                variant=item_data['variant'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                discount_amount=item_data['discount_amount'],
            )
            for item_data in order_items_data
        ]
        OrderItem.objects.bulk_create(order_items)

        # Deduct stock
        lines = [(item.variant_id, item.quantity) for item in order_items]
        reserved_lines = [
            (variant_id, qty)
            for variant_id, qty in lines
            if reservation and variant_id in reservation_items_map
        ]
        walk_in_lines = [
            (variant_id, qty)
            for variant_id, qty in lines
            if not reservation or variant_id not in reservation_items_map
        ]

        if reserved_lines:
            apply_movements(
                branch=branch,
                lines=reserved_lines,
                movement_type=MovementType.OUT_SALE_RESERVED,
                reference_type=ReferenceType.ORDER,
                reference_id=order.id,
                user=cashier,
                note=f"Venta POS reserva {order.code}",
            )

        if walk_in_lines:
            apply_movements(
                branch=branch,
                lines=walk_in_lines,
                movement_type=MovementType.OUT_SALE,
                reference_type=ReferenceType.ORDER,
                reference_id=order.id,
                user=cashier,
                note=f"Venta POS {order.code}",
            )

        # Finalize reservation (partial or full purchase)
        if reservation:
            from reservations.services import complete_reservation_pos_sale

            reservation_sold_items = [
                item for item in items if item['variant_id'] in reservation_items_map
            ]
            complete_reservation_pos_sale(
                reservation_id=reservation.id,
                sold_items=reservation_sold_items,
                user=cashier,
            )

        # Create payment records
        from payments.models import Payment, PaymentStatus, PaymentMethod, PaymentProvider

        for payment_data in payment_rows:
            Payment.objects.create(
                order=order,
                method=payment_data['method'],
                provider=PaymentProvider.NONE,
                status=PaymentStatus.SUCCEEDED,
                amount=Decimal(str(payment_data['amount'])),
                received_amount=payment_data.get('received_amount'),
                change_amount=payment_data.get('change_amount'),
                paid_at=timezone.now(),
            )

    # Generate receipt for POS sale
    from payments.services import generate_receipt
    try:
        receipt = generate_receipt(order_id=order.id)
    except Exception as e:
        # Log error but don't fail the sale
        print(f"Failed to generate receipt for order {order.code}: {e}")

    # TODO: Send notification to customer if email provided
    # from notifications.services import send_order_confirmation
    # if customer and customer.user.email:
    #     send_order_confirmation(order_id=order.id)

    return order
