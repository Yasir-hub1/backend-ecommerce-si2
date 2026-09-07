"""Product image helpers."""

from __future__ import annotations

from django.db import transaction

from catalog.models import ProductImage
from catalog.services.media_cleanup import delete_field_file


@transaction.atomic
def ensure_single_primary_image(*, product_id: int, primary_image_id: int) -> None:
    """Keep only one primary image per product."""
    ProductImage.objects.filter(
        product_id=product_id,
        is_primary=True,
    ).exclude(pk=primary_image_id).update(is_primary=False)


def replace_product_image_file(*, instance: ProductImage, new_file) -> None:
    """Delete the previous file on disk before assigning a new upload."""
    if instance.image and instance.image.name:
        delete_field_file(instance.image)
    instance.image = new_file
