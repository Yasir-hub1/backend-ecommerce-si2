"""
Supplier services for FashionStore.

Handles purchase receipt confirmation and inventory intake.
"""
from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessError
from suppliers.models import PurchaseReceipt, PurchaseReceiptStatus
from inventory.services import apply_movements
from inventory.models import MovementType, ReferenceType


@transaction.atomic
def confirm_receipt(*, receipt_id: int, user) -> PurchaseReceipt:
    """
    Confirm a purchase receipt and add items to inventory.

    This generates IN_RECEIPT movements for all items in the receipt.

    Args:
        receipt_id: PurchaseReceipt ID
        user: User confirming the receipt (must be staff)

    Returns:
        Updated PurchaseReceipt instance

    Raises:
        BusinessError: If receipt is not in DRAFT status
    """
    # Lock the receipt row
    receipt = PurchaseReceipt.objects.select_for_update().get(pk=receipt_id)

    # Validate status
    if receipt.status != PurchaseReceiptStatus.DRAFT:
        raise BusinessError(
            code='INVALID_RECEIPT_STATUS',
            message=f'Solo se pueden confirmar recepciones en estado DRAFT. '
                    f'Estado actual: {receipt.get_status_display()}',
            status_code=400,
            details={'receipt_code': receipt.code, 'current_status': receipt.status}
        )

    # Prepare lines for inventory movement
    lines = [
        (item.variant_id, item.quantity)
        for item in receipt.items.select_related('variant')
    ]

    # Apply inventory movements (IN_RECEIPT)
    apply_movements(
        branch=receipt.branch,
        lines=lines,
        movement_type=MovementType.IN_RECEIPT,
        reference_type=ReferenceType.RECEIPT,
        reference_id=receipt.id,
        user=user,
        note=f"Recepción de proveedor {receipt.supplier.trade_name or receipt.supplier.legal_name}"
    )

    # Update receipt status
    receipt.status = PurchaseReceiptStatus.CONFIRMED
    receipt.received_at = timezone.now()
    receipt.received_by = user
    receipt.save(update_fields=['status', 'received_at', 'received_by', 'updated_at'])

    return receipt


@transaction.atomic
def cancel_receipt(*, receipt_id: int, reason: str = "") -> PurchaseReceipt:
    """
    Cancel a purchase receipt.

    Can only cancel DRAFT receipts (not yet confirmed).

    Args:
        receipt_id: PurchaseReceipt ID
        reason: Reason for cancellation

    Returns:
        Updated PurchaseReceipt instance

    Raises:
        BusinessError: If receipt is already confirmed
    """
    receipt = PurchaseReceipt.objects.select_for_update().get(pk=receipt_id)

    if receipt.status != PurchaseReceiptStatus.DRAFT:
        raise BusinessError(
            code='CANNOT_CANCEL_RECEIPT',
            message='Solo se pueden cancelar recepciones en estado DRAFT.',
            status_code=400,
            details={'receipt_code': receipt.code, 'current_status': receipt.status}
        )

    receipt.status = PurchaseReceiptStatus.CANCELLED
    if reason:
        receipt.notes = f"{receipt.notes}\n\nCANCELADO: {reason}".strip()
    receipt.save(update_fields=['status', 'notes', 'updated_at'])

    return receipt
