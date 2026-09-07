"""
Payment services for FashionStore.

Handles Stripe Checkout Sessions, webhook processing, refunds, and receipt generation.
"""
import logging
from decimal import Decimal
from io import BytesIO
from typing import Dict, Optional

import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessError
from orders.models import Order, OrderStatus
from payments.models import (
    Payment,
    PaymentMethod,
    PaymentProvider,
    PaymentStatus,
    Receipt,
    StripeWebhookEvent,
)

logger = logging.getLogger(__name__)


def _build_checkout_metadata(order: Order) -> Dict[str, str]:
    metadata = {
        'order_id': str(order.id),
        'order_code': order.code,
        'branch_code': order.branch.code,
        'channel': order.channel,
    }
    if order.customer:
        metadata['customer_email'] = order.customer.user.email
    return metadata


def _build_checkout_line_items(order: Order) -> list:
    """Build Stripe line items that match order.grand_total."""
    amount_cents = int(order.grand_total * 100)
    return [
        {
            'price_data': {
                'currency': order.currency.lower(),
                'unit_amount': amount_cents,
                'product_data': {
                    'name': f'Orden {order.code}',
                    'description': f'FashionStore · {order.branch.name}',
                },
            },
            'quantity': 1,
        }
    ]


@transaction.atomic
def create_stripe_checkout_session(
    *,
    order_id: int,
) -> Dict:
    """
    Create a Stripe Checkout Session (ui_mode=elements) for an order.

    Uses Checkout Sessions + Payment Element instead of standalone PaymentIntents.
    Amount is always computed server-side from Order.grand_total.
    """
    order = (
        Order.objects.select_for_update(of=('self',))
        .select_related('customer__user', 'branch')
        .get(pk=order_id)
    )

    if order.status != OrderStatus.PENDING_PAYMENT:
        raise BusinessError(
            code='INVALID_ORDER_STATUS',
            message=f'La orden no está pendiente de pago. Estado: {order.get_status_display()}',
            status_code=400,
            details={'order_code': order.code, 'current_status': order.status},
        )

    metadata = _build_checkout_metadata(order)
    return_url = (
        f'{settings.FRONTEND_URL.rstrip("/")}'
        f'/ecommerce/checkout/resultado?session_id={{CHECKOUT_SESSION_ID}}'
    )

    session_params: Dict = {
        'ui_mode': 'elements',
        'mode': 'payment',
        'line_items': _build_checkout_line_items(order),
        'return_url': return_url,
        'metadata': metadata,
        'payment_intent_data': {'metadata': metadata},
    }

    if order.customer:
        session_params['customer_email'] = order.customer.user.email

    try:
        checkout_session = stripe.checkout.Session.create(**session_params)

        payment = Payment.objects.create(
            order=order,
            method=PaymentMethod.CARD_ONLINE,
            provider=PaymentProvider.STRIPE,
            status=PaymentStatus.PENDING,
            amount=order.grand_total,
            raw_response={'checkout_session_id': checkout_session.id},
        )

        return {
            'checkout_session_id': checkout_session.id,
            'client_secret': checkout_session.client_secret,
            'publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
            'amount': order.grand_total,
            'currency': order.currency,
            'payment_id': payment.id,
        }

    except stripe.error.StripeError as err:
        raise BusinessError(
            code='STRIPE_ERROR',
            message=f'Error al crear sesión de pago: {err}',
            status_code=500,
            details={'stripe_error': str(err)},
        ) from err


@transaction.atomic
def create_stripe_payment_intent(*, order_id: int) -> Dict:
    """PaymentIntent for mobile PaymentSheet. Reuses a pending intent if it exists."""
    order = (
        Order.objects.select_for_update(of=('self',))
        .select_related('customer__user', 'branch')
        .get(pk=order_id)
    )

    if order.status != OrderStatus.PENDING_PAYMENT:
        raise BusinessError(
            code='INVALID_ORDER_STATUS',
            message=f'La orden no está pendiente de pago. Estado: {order.get_status_display()}',
            status_code=400,
            details={'order_code': order.code, 'current_status': order.status},
        )

    pending = (
        Payment.objects.filter(
            order=order,
            method=PaymentMethod.CARD_ONLINE,
            provider=PaymentProvider.STRIPE,
            status=PaymentStatus.PENDING,
        )
        .order_by('-created_at')
        .first()
    )

    try:
        if pending and pending.provider_payment_intent_id:
            intent = stripe.PaymentIntent.retrieve(pending.provider_payment_intent_id)
            if intent.status in {'requires_payment_method', 'requires_confirmation', 'requires_action'}:
                return {
                    'client_secret': intent.client_secret,
                    'publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
                    'amount': order.grand_total,
                    'currency': order.currency,
                    'payment_id': pending.id,
                    'order_code': order.code,
                }

        metadata = _build_checkout_metadata(order)
        intent = stripe.PaymentIntent.create(
            amount=int(order.grand_total * 100),
            currency=order.currency.lower(),
            metadata=metadata,
            automatic_payment_methods={'enabled': True},
        )
        payment = Payment.objects.create(
            order=order,
            method=PaymentMethod.CARD_ONLINE,
            provider=PaymentProvider.STRIPE,
            status=PaymentStatus.PENDING,
            amount=order.grand_total,
            provider_payment_intent_id=intent.id,
            raw_response={'payment_intent_id': intent.id},
        )
        return {
            'client_secret': intent.client_secret,
            'publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
            'amount': order.grand_total,
            'currency': order.currency,
            'payment_id': payment.id,
            'order_code': order.code,
        }
    except stripe.error.StripeError as err:
        raise BusinessError(
            code='STRIPE_ERROR',
            message=f'Error al crear PaymentIntent: {err}',
            status_code=500,
            details={'stripe_error': str(err)},
        ) from err


def get_stripe_checkout_session_status(*, session_id: str) -> Dict:
    """Retrieve Checkout Session status from Stripe."""
    try:
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=['payment_intent'],
        )
    except stripe.error.StripeError as err:
        raise BusinessError(
            code='STRIPE_ERROR',
            message=f'Error al consultar sesión de pago: {err}',
            status_code=400,
            details={'stripe_error': str(err)},
        ) from err

    payment_intent = session.payment_intent
    payment_intent_id = None
    payment_intent_status = None
    if payment_intent and not isinstance(payment_intent, str):
        payment_intent_id = payment_intent.id
        payment_intent_status = payment_intent.status

    return {
        'id': session.id,
        'status': session.status,
        'payment_status': session.payment_status,
        'order_code': (session.metadata or {}).get('order_code'),
        'payment_intent_id': payment_intent_id,
        'payment_intent_status': payment_intent_status,
    }


def _find_payment_for_intent(payment_intent: Dict) -> Payment:
    payment_intent_id = payment_intent['id']

    try:
        return Payment.objects.select_related('order').get(
            provider_payment_intent_id=payment_intent_id
        )
    except Payment.DoesNotExist:
        metadata = payment_intent.get('metadata') or {}
        order_id = metadata.get('order_id')
        if not order_id:
            raise BusinessError(
                code='PAYMENT_NOT_FOUND',
                message=f'No se encontró pago para PaymentIntent {payment_intent_id}',
                status_code=404,
            ) from None

        payment = (
            Payment.objects.select_related('order')
            .filter(order_id=order_id, status=PaymentStatus.PENDING)
            .order_by('-created_at')
            .first()
        )
        if not payment:
            raise BusinessError(
                code='PAYMENT_NOT_FOUND',
                message=f'No se encontró pago pendiente para orden {order_id}',
                status_code=404,
            )

        payment.provider_payment_intent_id = payment_intent_id
        payment.save(update_fields=['provider_payment_intent_id', 'updated_at'])
        return payment


@transaction.atomic
def handle_stripe_webhook(
    *,
    payload: bytes,
    signature: str,
) -> Dict:
    """
    Handle Stripe webhook events with idempotent processing.
    """
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(payload, signature, webhook_secret)
    except ValueError as err:
        raise BusinessError(
            code='INVALID_PAYLOAD',
            message='Payload de webhook inválido',
            status_code=400,
        ) from err
    except stripe.error.SignatureVerificationError as err:
        raise BusinessError(
            code='INVALID_SIGNATURE',
            message='Firma de webhook inválida',
            status_code=400,
        ) from err

    event_id = event['id']
    event_type = event['type']

    if StripeWebhookEvent.objects.filter(event_id=event_id).exists():
        return {
            'status': 'already_processed',
            'event_id': event_id,
            'event_type': event_type,
        }

    webhook_event = StripeWebhookEvent.objects.create(
        event_id=event_id,
        event_type=event_type,
        payload=event,
    )

    result = {'status': 'received', 'event_id': event_id, 'event_type': event_type}

    try:
        if event_type == 'checkout.session.completed':
            result.update(_handle_checkout_session_completed(event))
        elif event_type == 'payment_intent.succeeded':
            result.update(_handle_payment_succeeded(event))
        elif event_type == 'payment_intent.payment_failed':
            result.update(_handle_payment_failed(event))
        elif event_type == 'charge.refunded':
            result.update(_handle_charge_refunded(event))
        else:
            result['status'] = 'ignored'

        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=['processed_at', 'updated_at'])

    except Exception as err:
        webhook_event.error = str(err)
        webhook_event.save(update_fields=['error', 'updated_at'])
        raise

    return result


def _handle_checkout_session_completed(event: Dict) -> Dict:
    """Link Checkout Session to pending Payment before PI webhook arrives."""
    session = event['data']['object']
    order_id = (session.get('metadata') or {}).get('order_id')
    payment_intent_id = session.get('payment_intent')

    if order_id and payment_intent_id:
        payment = (
            Payment.objects.filter(order_id=order_id, status=PaymentStatus.PENDING)
            .order_by('-created_at')
            .first()
        )
        if payment and not payment.provider_payment_intent_id:
            payment.provider_payment_intent_id = payment_intent_id
            payment.save(update_fields=['provider_payment_intent_id', 'updated_at'])

    return {
        'status': 'checkout_session_completed',
        'order_id': order_id,
        'payment_status': session.get('payment_status'),
    }


def _payment_intent_payload(intent) -> Dict:
    """Normalize Stripe PaymentIntent (SDK object or dict) for finalize helpers."""
    if isinstance(intent, dict):
        return intent
    return {
        'id': intent.id,
        'status': intent.status,
        'metadata': dict(intent.metadata or {}),
        'latest_charge': intent.latest_charge,
    }


def _finalize_succeeded_payment(*, payment: Payment, payment_intent: Dict) -> Dict:
    """
    Mark payment + order as paid and generate receipt.

    Idempotent: safe if webhook and client confirm race.
    """
    if payment.status != PaymentStatus.SUCCEEDED:
        payment.status = PaymentStatus.SUCCEEDED
        payment.paid_at = timezone.now()
        charge_id = payment_intent.get('latest_charge')
        if isinstance(charge_id, str):
            payment.provider_charge_id = charge_id
        elif charge_id is not None and hasattr(charge_id, 'id'):
            payment.provider_charge_id = charge_id.id
        payment.save(
            update_fields=['status', 'paid_at', 'provider_charge_id', 'updated_at']
        )

    from orders.services import mark_order_as_paid

    paid_statuses = {
        OrderStatus.PAID,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        OrderStatus.DELIVERED,
    }

    order = Order.objects.select_related('branch', 'customer').get(pk=payment.order_id)

    if order.status == OrderStatus.PENDING_PAYMENT:
        try:
            order = mark_order_as_paid(order_id=payment.order_id, payment=payment)
        except BusinessError as err:
            order.refresh_from_db()
            if order.status not in paid_statuses:
                return {
                    'status': 'payment_succeeded_but_order_cancelled',
                    'order_code': order.code,
                    'reason': err.message,
                    'payment_id': payment.id,
                }

    receipt = None
    if order.status in paid_statuses:
        try:
            if hasattr(order, 'receipt') and order.receipt:
                receipt = order.receipt
            else:
                receipt = generate_receipt(order_id=order.id)
        except Exception as err:
            logger.exception(
                'Error generating receipt for order %s: %s', order.code, err
            )

    return {
        'status': 'payment_succeeded',
        'order_code': order.code,
        'order_id': order.id,
        'order_status': order.status,
        'payment_id': payment.id,
        'receipt_id': receipt.id if receipt else None,
    }


def _handle_payment_succeeded(event: Dict) -> Dict:
    payment_intent = event['data']['object']
    payment = _find_payment_for_intent(payment_intent)
    return _finalize_succeeded_payment(
        payment=payment,
        payment_intent=payment_intent,
    )


@transaction.atomic
def confirm_stripe_payment_intent(*, order_id: int) -> Dict:
    """
    Client-side confirmation after PaymentSheet succeeds.

    Stripe may charge before the webhook reaches localhost; this polls Stripe
    and applies the same finalize path as payment_intent.succeeded.
    """
    try:
        order = Order.objects.select_related('customer', 'branch').get(pk=order_id)
    except Order.DoesNotExist as err:
        raise BusinessError(
            code='ORDER_NOT_FOUND',
            message='Orden no encontrada',
            status_code=404,
        ) from err

    paid_statuses = {
        OrderStatus.PAID,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        OrderStatus.DELIVERED,
    }
    if order.status in paid_statuses:
        receipt = None
        try:
            if hasattr(order, 'receipt') and order.receipt:
                receipt = order.receipt
            else:
                receipt = generate_receipt(order_id=order.id)
        except Exception as err:
            logger.exception(
                'Error generating receipt for order %s: %s', order.code, err
            )
        return {
            'status': 'already_paid',
            'order_code': order.code,
            'order_id': order.id,
            'order_status': order.status,
            'receipt_id': receipt.id if receipt else None,
        }

    if order.status != OrderStatus.PENDING_PAYMENT:
        raise BusinessError(
            code='INVALID_ORDER_STATUS',
            message=(
                f'La orden no está pendiente de pago. '
                f'Estado: {order.get_status_display()}'
            ),
            status_code=400,
            details={'order_code': order.code, 'current_status': order.status},
        )

    payment = (
        Payment.objects.select_related('order')
        .filter(
            order=order,
            method=PaymentMethod.CARD_ONLINE,
            provider=PaymentProvider.STRIPE,
            status__in={PaymentStatus.PENDING, PaymentStatus.SUCCEEDED},
        )
        .order_by('-created_at')
        .first()
    )
    if not payment or not payment.provider_payment_intent_id:
        raise BusinessError(
            code='PAYMENT_NOT_FOUND',
            message='No hay PaymentIntent pendiente para esta orden',
            status_code=404,
            details={'order_code': order.code},
        )

    try:
        intent = stripe.PaymentIntent.retrieve(payment.provider_payment_intent_id)
    except stripe.error.StripeError as err:
        raise BusinessError(
            code='STRIPE_ERROR',
            message=f'Error al consultar PaymentIntent: {err}',
            status_code=502,
            details={'stripe_error': str(err)},
        ) from err

    pi = _payment_intent_payload(intent)

    if intent.status == 'succeeded':
        return _finalize_succeeded_payment(payment=payment, payment_intent=pi)

    if intent.status in {'processing', 'requires_capture'}:
        return {
            'status': 'processing',
            'order_code': order.code,
            'order_id': order.id,
            'order_status': order.status,
            'payment_intent_status': intent.status,
        }

    if intent.status in {'canceled', 'requires_payment_method'}:
        if payment.status == PaymentStatus.PENDING:
            payment.status = PaymentStatus.FAILED
            payment.save(update_fields=['status', 'updated_at'])
        raise BusinessError(
            code='PAYMENT_NOT_COMPLETED',
            message='El pago no se completó en Stripe',
            status_code=400,
            details={
                'order_code': order.code,
                'payment_intent_status': intent.status,
            },
        )

    raise BusinessError(
        code='PAYMENT_NOT_COMPLETED',
        message='El pago aún no está confirmado en Stripe',
        status_code=400,
        details={
            'order_code': order.code,
            'payment_intent_status': intent.status,
        },
    )


def _handle_payment_failed(event: Dict) -> Dict:
    payment_intent = event['data']['object']

    try:
        payment = _find_payment_for_intent(payment_intent)
    except BusinessError:
        return {'status': 'payment_not_found'}

    payment.status = PaymentStatus.FAILED
    payment.save(update_fields=['status', 'updated_at'])

    return {
        'status': 'payment_failed',
        'payment_id': payment.id,
        'order_code': payment.order.code,
    }


def _handle_charge_refunded(event: Dict) -> Dict:
    charge = event['data']['object']
    charge_id = charge['id']

    try:
        payment = Payment.objects.get(provider_charge_id=charge_id)
    except Payment.DoesNotExist:
        return {'status': 'payment_not_found'}

    payment.status = PaymentStatus.REFUNDED
    payment.save(update_fields=['status', 'updated_at'])

    return {
        'status': 'refunded',
        'payment_id': payment.id,
        'order_code': payment.order.code,
    }


@transaction.atomic
def process_stripe_refund(
    *,
    payment_id: int,
    amount: Optional[Decimal] = None,
    reason: str = "",
) -> Dict:
    """
    Process a refund through Stripe.
    """
    payment = Payment.objects.select_for_update().select_related('order').get(pk=payment_id)

    if payment.status != PaymentStatus.SUCCEEDED:
        raise BusinessError(
            code='CANNOT_REFUND',
            message='Solo se pueden reembolsar pagos exitosos',
            status_code=400,
            details={'payment_id': payment_id, 'current_status': payment.status},
        )

    if not payment.provider_charge_id:
        raise BusinessError(
            code='NO_CHARGE_ID',
            message='No hay ID de cargo de Stripe para reembolsar',
            status_code=400,
        )

    refund_amount = amount if amount else payment.amount
    amount_cents = int(refund_amount * 100)

    try:
        refund = stripe.Refund.create(
            charge=payment.provider_charge_id,
            amount=amount_cents,
            reason='requested_by_customer',
            metadata={
                'order_code': payment.order.code,
                'reason': reason,
            },
        )

        payment.status = PaymentStatus.REFUNDED
        payment.save(update_fields=['status', 'updated_at'])

        return {
            'refund_id': refund.id,
            'amount': refund_amount,
            'currency': payment.order.currency,
            'payment_id': payment.id,
            'order_code': payment.order.code,
        }

    except stripe.error.StripeError as err:
        raise BusinessError(
            code='STRIPE_REFUND_ERROR',
            message=f'Error al procesar reembolso: {err}',
            status_code=500,
            details={'stripe_error': str(err)},
        ) from err


@transaction.atomic
def generate_receipt(
    *,
    order_id: int,
) -> Receipt:
    """
    Generate PDF receipt for a paid order.
    """
    from django.template.loader import render_to_string
    from weasyprint import HTML

    order = Order.objects.select_related(
        'customer__user',
        'branch__city',
        'reservation',
    ).prefetch_related(
        'items__variant__product',
        'items__variant__size',
        'items__variant__color',
        'payments',
    ).get(pk=order_id)

    if order.status not in [
        OrderStatus.PAID,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        OrderStatus.DELIVERED,
    ]:
        raise BusinessError(
            code='ORDER_NOT_PAID',
            message='Solo se pueden generar comprobantes para órdenes pagadas',
            status_code=400,
            details={'order_code': order.code, 'current_status': order.status},
        )

    existing_receipt = Receipt.objects.filter(order=order).first()
    if existing_receipt:
        return existing_receipt

    last_receipt = (
        Receipt.objects.filter(branch=order.branch)
        .order_by('-number')
        .first()
    )
    next_number = (last_receipt.number + 1) if last_receipt else 1
    receipt_number = f'{order.branch.code}-{next_number:06d}'

    context = {
        'receipt_number': receipt_number,
        'order': order,
        'items': order.items.all(),
        'payments': order.payments.filter(status=PaymentStatus.SUCCEEDED),
        'total_paid': sum(
            p.amount for p in order.payments.filter(status=PaymentStatus.SUCCEEDED)
        ),
        'generated_at': timezone.now(),
        'company': {
            'name': 'FashionStore',
            'nit': '123456789',
            'address': 'Dirección principal',
            'phone': '+591 1234567',
        },
    }

    html_string = render_to_string('receipts/receipt.html', context)

    pdf_file = BytesIO()
    HTML(string=html_string).write_pdf(pdf_file)
    pdf_file.seek(0)

    receipt = Receipt.objects.create(
        order=order,
        number=next_number,
        branch=order.branch,
    )

    from django.core.files.base import ContentFile

    receipt.pdf_file.save(
        f'{receipt_number}.pdf',
        ContentFile(pdf_file.getvalue()),
        save=True,
    )

    return receipt


def validate_pos_payment(
    *,
    total_due: Decimal,
    payments: list,
) -> Dict:
    """
    Validate POS payment before creating order.
    """
    total_payment = sum(Decimal(str(p['amount'])) for p in payments)

    if total_payment < total_due:
        raise BusinessError(
            code='INSUFFICIENT_PAYMENT',
            message=f'Pago insuficiente. Total: {total_due}, Recibido: {total_payment}',
            status_code=400,
            details={
                'total_due': str(total_due),
                'total_payment': str(total_payment),
                'shortfall': str(total_due - total_payment),
            },
        )

    total_change = Decimal('0')

    for payment in payments:
        if payment['method'] == PaymentMethod.CASH:
            received = Decimal(str(payment.get('received_amount', payment['amount'])))
            amount = Decimal(str(payment['amount']))

            if received > amount:
                change = received - amount
                payment['change_amount'] = change
                total_change += change
            else:
                payment['change_amount'] = Decimal('0')
        else:
            payment['change_amount'] = Decimal('0')

    return {
        'valid': True,
        'total_payment': total_payment,
        'total_change': total_change,
        'overpayment': total_payment - total_due,
    }
