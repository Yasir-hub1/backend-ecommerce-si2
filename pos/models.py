"""
Point of Sale models for FashionStore.

POS sales use the Order model with channel=POS.
This module only contains POS-specific utilities if needed.

All actual sales data lives in:
- orders.Order (with channel=POS)
- payments.Payment (with method=CASH or CARD_POS)
"""

# POS operations use existing models from orders and payments apps
# No additional models needed here
