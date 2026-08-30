"""Product image helpers."""
from django.db import transaction

from catalog.models import ProductImage


@transaction.atomic
def ensure_single_primary_image(*, product_id: int, primary_image_id: int) -> None:
    """Keep only one primary image per product."""
    ProductImage.objects.filter(
        product_id=product_id,
        is_primary=True,
    ).exclude(pk=primary_image_id).update(is_primary=False)
