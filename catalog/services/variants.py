"""Product variant bulk operations."""
from django.db import transaction

from catalog.models import Color, Product, ProductVariant, Size
from core.exceptions import BusinessError


@transaction.atomic
def generate_product_variants(
    *,
    product_id: int,
    size_ids: list[int],
    color_ids: list[int],
    skip_existing: bool = True,
) -> dict:
    product = Product.objects.get(pk=product_id)
    sizes = list(Size.objects.filter(id__in=size_ids))
    colors = list(Color.objects.filter(id__in=color_ids))

    if len(sizes) != len(set(size_ids)):
        raise BusinessError(
            code='INVALID_SIZES',
            message='Una o más tallas no existen',
            status_code=400,
        )
    if len(colors) != len(set(color_ids)):
        raise BusinessError(
            code='INVALID_COLORS',
            message='Uno o más colores no existen',
            status_code=400,
        )

    created = []
    skipped = []

    for size in sizes:
        for color in colors:
            exists = ProductVariant.objects.filter(
                product=product,
                size=size,
                color=color,
            ).exists()
            if exists:
                if skip_existing:
                    skipped.append({'size_id': size.id, 'color_id': color.id})
                    continue
                raise BusinessError(
                    code='VARIANT_EXISTS',
                    message=f'Ya existe variante {size.code}/{color.name}',
                    status_code=400,
                )

            variant = ProductVariant.objects.create(
                product=product,
                size=size,
                color=color,
            )
            created.append(variant)

    return {
        'created_count': len(created),
        'skipped_count': len(skipped),
        'variants': created,
    }
