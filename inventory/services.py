"""
Inventory services for FashionStore.

This is the CORE of the transactional system.
All inventory operations MUST go through these services.
"""
from typing import List, Tuple, Optional
from django.db import transaction
from django.db.models import F

from core.exceptions import BusinessError
from inventory.models import (
    BranchStock,
    InventoryMovement,
    MovementType,
    ReferenceType,
)


# Movement type effects on (on_hand, reserved)
MOVEMENT_EFFECTS = {
    MovementType.IN_RECEIPT: (+1, 0),
    MovementType.RESERVE_HOLD: (0, +1),
    MovementType.RESERVE_RELEASE: (0, -1),
    MovementType.OUT_SALE: (-1, 0),
    MovementType.OUT_SALE_RESERVED: (-1, -1),
    MovementType.RETURN_IN: (+1, 0),
    MovementType.ADJUST_IN: (+1, 0),
    MovementType.ADJUST_OUT: (-1, 0),
    MovementType.TRANSFER_IN: (+1, 0),
    MovementType.TRANSFER_OUT: (-1, 0),
}


@transaction.atomic
def apply_movements(
    *,
    branch,
    lines: List[Tuple[int, int]],  # [(variant_id, quantity), ...]
    movement_type: str,
    reference_type: str,
    reference_id: Optional[int] = None,
    user=None,
    note: str = "",
) -> List[InventoryMovement]:
    """
    Apply inventory movements atomically.

    This function is the ONLY way to modify inventory.
    It ensures:
    - All movements are atomic (all or nothing)
    - Stock levels never go negative
    - Reserved never exceeds on_hand
    - Deadlock prevention via deterministic locking order

    Args:
        branch: Branch instance
        lines: List of (variant_id, quantity) tuples
        movement_type: One of MovementType constants
        reference_type: One of ReferenceType constants
        reference_id: ID of the source document (Order, Reservation, etc.)
        user: User performing the operation
        note: Optional note for audit trail

    Returns:
        List of created InventoryMovement instances

    Raises:
        BusinessError: If movement would result in invalid stock levels
        KeyError: If movement_type is not valid
    """
    # Get effect multipliers for this movement type
    try:
        delta_on_hand, delta_reserved = MOVEMENT_EFFECTS[movement_type]
    except KeyError:
        raise ValueError(f"Invalid movement_type: {movement_type}")

    # Sort variant_ids to prevent deadlocks
    # If two transactions try to lock (variant_A, variant_B) and (variant_B, variant_A)
    # in different orders, they will deadlock. Sorting ensures consistent order.
    variant_ids = sorted(set(v_id for v_id, _ in lines))

    # Lock all stock records in deterministic order
    # select_for_update() acquires row-level locks
    stocks_dict = {
        stock.variant_id: stock
        for stock in BranchStock.objects.select_for_update()
        .filter(branch=branch, variant_id__in=variant_ids)
        .order_by('variant_id')  # Critical: deterministic order
    }

    movements = []

    for variant_id, quantity in lines:
        # Get or create stock record (locked)
        stock = stocks_dict.get(variant_id)
        if not stock:
            # Create new stock record if it doesn't exist
            stock, _ = BranchStock.objects.select_for_update().get_or_create(
                branch=branch,
                variant_id=variant_id,
                defaults={'on_hand': 0, 'reserved': 0}
            )

        # Calculate new values
        new_on_hand = stock.on_hand + (delta_on_hand * quantity)
        new_reserved = stock.reserved + (delta_reserved * quantity)

        # Validate new values (these constraints MUST hold)
        if new_on_hand < 0:
            raise BusinessError(
                code='INSUFFICIENT_STOCK',
                message=f'Stock insuficiente: se requieren {quantity} unidades, '
                        f'pero solo hay {stock.on_hand} disponibles.',
                status_code=409,
                details={
                    'variant_id': variant_id,
                    'branch_code': branch.code,
                    'requested': quantity,
                    'available': stock.on_hand,
                }
            )

        if new_reserved < 0:
            raise BusinessError(
                code='INVALID_RESERVATION',
                message=f'Reserva inválida: no se pueden liberar {abs(delta_reserved * quantity)} unidades, '
                        f'solo hay {stock.reserved} reservadas.',
                status_code=409,
                details={
                    'variant_id': variant_id,
                    'branch_code': branch.code,
                    'requested_release': abs(delta_reserved * quantity),
                    'currently_reserved': stock.reserved,
                }
            )

        if new_reserved > new_on_hand:
            raise BusinessError(
                code='RESERVED_EXCEEDS_ON_HAND',
                message=f'Las unidades reservadas ({new_reserved}) no pueden exceder '
                        f'las unidades en mano ({new_on_hand}).',
                status_code=409,
                details={
                    'variant_id': variant_id,
                    'branch_code': branch.code,
                    'new_reserved': new_reserved,
                    'new_on_hand': new_on_hand,
                }
            )

        # Apply the changes
        stock.on_hand = new_on_hand
        stock.reserved = new_reserved
        stock.save(update_fields=['on_hand', 'reserved', 'updated_at'])

        # Create movement record (append-only ledger)
        movement = InventoryMovement(
            branch=branch,
            variant_id=variant_id,
            movement_type=movement_type,
            quantity=quantity,
            reference_type=reference_type,
            reference_id=reference_id,
            created_by=user,
            note=note,
        )
        movements.append(movement)

    # Bulk create all movements
    InventoryMovement.objects.bulk_create(movements)

    return movements


def check_availability(
    *,
    branch,
    variant_id: int,
    quantity: int = 1,
) -> bool:
    """
    Check if there's enough available stock for a variant.

    Available = on_hand - reserved

    Args:
        branch: Branch instance
        variant_id: Product variant ID
        quantity: Required quantity

    Returns:
        True if enough stock is available, False otherwise
    """
    try:
        stock = BranchStock.objects.get(branch=branch, variant_id=variant_id)
        available = stock.on_hand - stock.reserved
        return available >= quantity
    except BranchStock.DoesNotExist:
        return False


def get_stock_levels(*, branch, variant_id: int) -> dict:
    """
    Get current stock levels for a variant at a branch.

    Args:
        branch: Branch instance
        variant_id: Product variant ID

    Returns:
        dict with on_hand, reserved, and available counts
    """
    try:
        stock = BranchStock.objects.get(branch=branch, variant_id=variant_id)
        return {
            'on_hand': stock.on_hand,
            'reserved': stock.reserved,
            'available': stock.on_hand - stock.reserved,
        }
    except BranchStock.DoesNotExist:
        return {
            'on_hand': 0,
            'reserved': 0,
            'available': 0,
        }


def get_total_stock(*, variant_id: int) -> dict:
    """
    Get total stock across all branches for a variant.

    Args:
        variant_id: Product variant ID

    Returns:
        dict with total on_hand, reserved, and available counts
    """
    stocks = BranchStock.objects.filter(variant_id=variant_id)

    total_on_hand = sum(s.on_hand for s in stocks)
    total_reserved = sum(s.reserved for s in stocks)

    return {
        'total_on_hand': total_on_hand,
        'total_reserved': total_reserved,
        'total_available': total_on_hand - total_reserved,
        'branches': [
            {
                'branch_id': s.branch_id,
                'branch_code': s.branch.code,
                'branch_name': s.branch.name,
                'on_hand': s.on_hand,
                'reserved': s.reserved,
                'available': s.on_hand - s.reserved,
            }
            for s in stocks.select_related('branch')
        ]
    }
