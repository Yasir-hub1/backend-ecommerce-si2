"""Order receipt helpers."""
from django.http import Http404

from core.exceptions import BusinessError
from orders.models import Order, OrderStatus
from payments.models import Receipt
from payments.services import generate_receipt


def receipt_number(receipt: Receipt) -> str:
    return f'{receipt.branch.code}-{receipt.number:06d}'


def user_can_access_order_receipt(*, user, order: Order) -> bool:
    from accounts.models import Role

    if user.role == Role.ADMIN:
        return True

    if user.role == Role.CUSTOMER:
        return order.customer is not None and order.customer.user_id == user.id

    if user.role in (Role.BRANCH_MANAGER, Role.CASHIER):
        try:
            return order.branch_id == user.employee_profile.branch_id
        except AttributeError:
            return False

    return False


def get_or_create_order_receipt(*, order: Order) -> Receipt:
    if hasattr(order, 'receipt') and order.receipt:
        return order.receipt

    if order.status not in {
        OrderStatus.PAID,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        OrderStatus.DELIVERED,
    }:
        raise BusinessError(
            code='ORDER_NOT_PAID',
            message='Solo hay comprobante para órdenes pagadas',
            status_code=400,
            details={'order_code': order.code, 'current_status': order.status},
        )

    return generate_receipt(order_id=order.id)


def get_order_receipt(*, order: Order) -> Receipt:
    try:
        return get_or_create_order_receipt(order=order)
    except BusinessError as err:
        raise Http404(err.message) from err
