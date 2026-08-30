"""
Reservation services for FashionStore.

Handles reservation creation, transitions, cancellation, and expiration.
"""
from typing import List, Dict
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from django.conf import settings

from core.exceptions import BusinessError
from reservations.models import (
    Reservation,
    ReservationItem,
    ReservationStatus,
    ItemStatus,
)
from inventory.services import apply_movements, check_availability
from inventory.models import MovementType, ReferenceType


@transaction.atomic
def create_reservation(
    *,
    customer,
    branch,
    scheduled_for,
    items: List[Dict[str, int]],  # [{'variant_id': 1, 'quantity': 2}, ...]
    notes: str = "",
) -> Reservation:
    """
    Create a new reservation and hold stock.

    Workflow:
    1. Validate branch operating hours
    2. Check stock availability for all items
    3. Create reservation
    4. Apply RESERVE_HOLD movements (atomically)
    5. Create notification

    Args:
        customer: CustomerProfile instance
        branch: Branch instance
        scheduled_for: datetime when customer will arrive
        items: List of {'variant_id': int, 'quantity': int}
        notes: Optional notes

    Returns:
        Created Reservation instance

    Raises:
        BusinessError: If validation fails or insufficient stock
    """
    # Validate scheduled time is within branch hours
    scheduled_time = scheduled_for.time()
    if not (branch.opens_at <= scheduled_time <= branch.closes_at):
        raise BusinessError(
            code='INVALID_SCHEDULE',
            message=f'El horario debe estar entre {branch.opens_at} y {branch.closes_at}',
            status_code=400,
            details={
                'branch_code': branch.code,
                'opens_at': str(branch.opens_at),
                'closes_at': str(branch.closes_at),
            }
        )

    # Validate scheduled_for is in the future
    if scheduled_for <= timezone.now():
        raise BusinessError(
            code='INVALID_SCHEDULE',
            message='La fecha de reserva debe ser en el futuro',
            status_code=400,
        )

    # Check availability for all items BEFORE creating reservation
    unavailable_items = []
    for item in items:
        variant_id = item['variant_id']
        quantity = item['quantity']

        if not check_availability(branch=branch, variant_id=variant_id, quantity=quantity):
            unavailable_items.append({
                'variant_id': variant_id,
                'quantity': quantity,
            })

    if unavailable_items:
        raise BusinessError(
            code='INSUFFICIENT_STOCK',
            message='No hay stock suficiente para algunos artículos',
            status_code=409,
            details={'unavailable_items': unavailable_items}
        )

    # Calculate expiration time
    # Default: 24 hours after scheduled time or as configured
    expiry_hours = getattr(settings, 'RESERVATION_DEFAULT_EXPIRY_HOURS', 24)
    expires_at = scheduled_for + timedelta(hours=expiry_hours)

    # Create reservation
    reservation = Reservation.objects.create(
        customer=customer,
        branch=branch,
        scheduled_for=scheduled_for,
        expires_at=expires_at,
        status=ReservationStatus.PENDING,
        notes=notes,
    )

    # Create reservation items
    reservation_items = []
    for item in items:
        reservation_items.append(
            ReservationItem(
                reservation=reservation,
                variant_id=item['variant_id'],
                quantity=item['quantity'],
                item_status=ItemStatus.HELD,
            )
        )
    ReservationItem.objects.bulk_create(reservation_items)

    # Apply inventory movements (RESERVE_HOLD)
    # This locks the stock atomically
    lines = [(item['variant_id'], item['quantity']) for item in items]

    try:
        apply_movements(
            branch=branch,
            lines=lines,
            movement_type=MovementType.RESERVE_HOLD,
            reference_type=ReferenceType.RESERVATION,
            reference_id=reservation.id,
            user=customer.user,
            note=f"Reserva {reservation.code}"
        )
    except BusinessError:
        # If stock reservation fails, the entire transaction rolls back
        # including the reservation creation
        raise

    # TODO: Create notification for branch staff
    # from notifications.services import create_notification
    # create_notification(...)

    return reservation


@transaction.atomic
def transition_reservation(
    *,
    reservation_id: int,
    new_status: str,
    user,
) -> Reservation:
    """
    Transition reservation to a new status.

    Validates state machine transitions.

    Args:
        reservation_id: Reservation ID
        new_status: Target status
        user: User performing the transition

    Returns:
        Updated Reservation instance

    Raises:
        BusinessError: If transition is invalid
    """
    reservation = Reservation.objects.select_for_update().get(pk=reservation_id)

    # Validate transition
    valid_transitions = ReservationStatus.TRANSITIONS.get(reservation.status, [])
    if new_status not in valid_transitions:
        raise BusinessError(
            code='INVALID_TRANSITION',
            message=f'No se puede cambiar de {reservation.get_status_display()} '
                    f'a {dict(ReservationStatus.CHOICES).get(new_status, new_status)}',
            status_code=409,
            details={
                'current_status': reservation.status,
                'requested_status': new_status,
                'valid_transitions': valid_transitions,
            }
        )

    # Update status
    old_status = reservation.status
    reservation.status = new_status

    # Set prepared_by when transitioning to PREPARING
    if new_status == ReservationStatus.PREPARING and not reservation.prepared_by:
        reservation.prepared_by = user

    reservation.save(update_fields=['status', 'prepared_by', 'updated_at'])

    # TODO: Create notification based on status
    # if new_status == ReservationStatus.READY:
    #     notify customer that reservation is ready

    return reservation


@transaction.atomic
def cancel_reservation(
    *,
    reservation_id: int,
    reason: str = "",
) -> Reservation:
    """
    Cancel a reservation and release held stock.

    Only items still in HELD status will be released.

    Args:
        reservation_id: Reservation ID
        reason: Cancellation reason

    Returns:
        Updated Reservation instance
    """
    reservation = Reservation.objects.select_for_update().get(pk=reservation_id)

    # Can only cancel if not completed
    if reservation.status in [ReservationStatus.COMPLETED]:
        raise BusinessError(
            code='CANNOT_CANCEL',
            message='No se puede cancelar una reserva completada',
            status_code=400,
            details={'reservation_code': reservation.code}
        )

    # Get items still in HELD status
    held_items = reservation.items.filter(item_status=ItemStatus.HELD)

    if held_items.exists():
        # Release reserved stock
        lines = [(item.variant_id, item.quantity) for item in held_items]

        apply_movements(
            branch=reservation.branch,
            lines=lines,
            movement_type=MovementType.RESERVE_RELEASE,
            reference_type=ReferenceType.RESERVATION,
            reference_id=reservation.id,
            note=f"Cancelación de reserva {reservation.code}: {reason}"
        )

        # Update item status
        held_items.update(item_status=ItemStatus.RETURNED_TO_FLOOR)

    # Update reservation
    reservation.status = ReservationStatus.CANCELLED
    if reason:
        reservation.notes = f"{reservation.notes}\n\nCANCELADO: {reason}".strip()
    reservation.save(update_fields=['status', 'notes', 'updated_at'])

    return reservation


def expire_due_reservations():
    """
    Celery task to expire reservations that have passed their expiry time.

    Should run every 10 minutes via celery beat.
    """
    from django.db import transaction as db_transaction

    # Find expired reservations
    expired = Reservation.objects.filter(
        status__in=[
            ReservationStatus.PENDING,
            ReservationStatus.PREPARING,
            ReservationStatus.READY,
        ],
        expires_at__lte=timezone.now()
    )

    expired_count = 0

    for reservation in expired:
        try:
            with db_transaction.atomic():
                # Use cancel_reservation to properly release stock
                cancel_reservation(
                    reservation_id=reservation.id,
                    reason="Expiración automática"
                )
                # Override status to EXPIRED (after cancellation logic)
                reservation.status = ReservationStatus.EXPIRED
                reservation.save(update_fields=['status', 'updated_at'])
                expired_count += 1
        except Exception as e:
            # Log error but continue processing other reservations
            print(f"Error expiring reservation {reservation.code}: {e}")
            continue

    return expired_count


@transaction.atomic
def complete_reservation_pos_sale(
    *,
    reservation_id: int,
    sold_items: List[Dict],
    user,
) -> Reservation:
    """
    Finalize a reservation after a POS sale.

    Marks purchased lines, releases unsold reserved stock, completes reservation.
    """
    reservation = Reservation.objects.select_for_update().get(pk=reservation_id)

    if reservation.status not in (ReservationStatus.IN_FITTING, ReservationStatus.READY):
        raise BusinessError(
            code='INVALID_RESERVATION_STATUS',
            message='La reserva debe estar lista o en probador para cobrar',
            status_code=409,
            details={'current_status': reservation.status},
        )

    sold_map = {item['variant_id']: item['quantity'] for item in sold_items}
    reservation_items = list(reservation.items.select_for_update().all())
    release_lines: list[tuple[int, int]] = []

    for reservation_item in reservation_items:
        sold_qty = sold_map.get(reservation_item.variant_id, 0)

        if sold_qty > reservation_item.quantity:
            raise BusinessError(
                code='INVALID_RESERVATION_QUANTITY',
                message=(
                    f'Cantidad vendida mayor a la reservada para '
                    f'{reservation_item.variant.sku}'
                ),
                status_code=400,
            )

        if sold_qty == 0:
            if reservation_item.item_status == ItemStatus.HELD:
                release_lines.append((reservation_item.variant_id, reservation_item.quantity))
                reservation_item.item_status = ItemStatus.RETURNED_TO_FLOOR
                reservation_item.save(update_fields=['item_status', 'updated_at'])
            continue

        if sold_qty < reservation_item.quantity:
            remaining = reservation_item.quantity - sold_qty
            release_lines.append((reservation_item.variant_id, remaining))
            reservation_item.quantity = sold_qty

        reservation_item.item_status = ItemStatus.PURCHASED
        reservation_item.save(update_fields=['quantity', 'item_status', 'updated_at'])

    if release_lines:
        apply_movements(
            branch=reservation.branch,
            lines=release_lines,
            movement_type=MovementType.RESERVE_RELEASE,
            reference_type=ReferenceType.RESERVATION,
            reference_id=reservation.id,
            user=user,
            note=f'Artículos no comprados en reserva {reservation.code}',
        )

    reservation.status = ReservationStatus.COMPLETED
    reservation.save(update_fields=['status', 'updated_at'])
    return reservation
