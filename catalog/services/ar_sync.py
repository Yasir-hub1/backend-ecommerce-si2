"""Bridge catalog product photos → AR overlay processing."""

from __future__ import annotations

import logging
from pathlib import Path

from django.core.files.base import ContentFile

from catalog.models import ARAsset, ProductImage
from catalog.services.media_cleanup import delete_field_file

logger = logging.getLogger(__name__)


def _resolve_ar_asset(product_image: ProductImage) -> ARAsset:
    """
    Pick the OVERLAY_2D row to update — never create a second asset for the
    same product when a colored (or colorless) one already exists.
    """
    qs = ARAsset.objects.filter(
        product_id=product_image.product_id,
        kind=ARAsset.OVERLAY_2D,
    )
    if product_image.color_id:
        existing = qs.filter(color_id=product_image.color_id).first()
        if existing:
            return existing
        asset, _ = ARAsset.objects.get_or_create(
            product_id=product_image.product_id,
            color_id=product_image.color_id,
            kind=ARAsset.OVERLAY_2D,
            defaults={'status': ARAsset.PENDING, 'is_active': True, 'process_error': ''},
        )
        return asset

    # Catalog photo without color: prefer colorless asset, else the only colored one.
    existing = qs.filter(color_id__isnull=True).first()
    if existing:
        return existing
    colored = list(qs.order_by('id')[:2])
    if len(colored) == 1:
        return colored[0]
    if not colored:
        asset, _ = ARAsset.objects.get_or_create(
            product_id=product_image.product_id,
            color_id=None,
            kind=ARAsset.OVERLAY_2D,
            defaults={'status': ARAsset.PENDING, 'is_active': True, 'process_error': ''},
        )
        return asset
    # Multiple colored assets and no colorless — update the oldest.
    return colored[0]


def sync_ar_from_product_image(product_image: ProductImage) -> int | None:
    """
    Copy a catalog photo into ARAsset.source_image and enqueue rembg.

    One OVERLAY_2D asset per (product, color). Replaces previous source on disk.
    Returns the ARAsset id, or None if the catalog file is missing.
    """
    if product_image.image is None or not product_image.image.name:
        return None

    path = Path(product_image.image.path)
    if not path.exists():
        logger.warning(
            'Cannot sync AR for product_image=%s — file missing: %s',
            product_image.pk,
            path,
        )
        return None

    raw = path.read_bytes()
    if not raw:
        logger.warning('Empty catalog image for product_image=%s', product_image.pk)
        return None

    asset = _resolve_ar_asset(product_image)

    if asset.source_image:
        delete_field_file(asset.source_image)

    asset.source_image.save(path.name, ContentFile(raw), save=False)
    asset.status = ARAsset.PENDING
    asset.process_error = ''
    asset.is_active = True
    asset.save()

    from catalog.tasks import enqueue_ar_asset_build

    task_id = enqueue_ar_asset_build(asset.id)
    logger.info(
        'Synced product_image=%s → AR asset=%s (task=%s)',
        product_image.pk,
        asset.id,
        task_id,
    )
    return asset.id
