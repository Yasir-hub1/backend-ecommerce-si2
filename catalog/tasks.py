"""Celery tasks for catalog, including AR overlay processing."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def build_ar_asset(asset_id: int) -> None:
    from pathlib import Path

    from catalog.models import ARAsset
    from catalog.services.ar_assets import (
        apply_processed_bytes,
        copy_catalog_image_as_source,
        process_garment_image,
    )

    asset = ARAsset.objects.select_related('color', 'product').get(pk=asset_id)
    asset.status = ARAsset.PROCESSING
    asset.process_error = ''
    asset.save(update_fields=['status', 'process_error', 'updated_at'])

    try:
        # Prefer source_image; fall back to catalogphoto when missing.
        source = None
        if asset.source_image:
            src_path = Path(asset.source_image.path)
            if src_path.exists():
                source = asset.source_image
            else:
                logger.warning('AR asset %s source_image missing on disk (%s), copying from catalog', asset_id, src_path)

        if source is None:
            copied = copy_catalog_image_as_source(asset)
            if copied:
                asset.save(update_fields=['source_image', 'updated_at'])
                source = asset.source_image
                logger.info('AR asset %s: copied catalog image as source', asset_id)

        if source is None:
            raise ValueError(
                'Sin imagen de origen. Sube la foto de la prenda desde el panel de administración.'
            )

        raw = source.read()
        source.seek(0)
        if not raw:
            raise ValueError('El archivo de origen está vacío.')

        png, anchor = process_garment_image(raw)
        apply_processed_bytes(asset=asset, png=png, anchor=anchor)
        asset.save()
        logger.info('AR asset %s processed OK — %d bytes, status=READY', asset_id, len(png))
    except Exception as err:
        logger.exception('AR asset %s failed: %s', asset_id, err)
        asset.status = ARAsset.FAILED
        asset.process_error = str(err)[:1000]
        asset.save(update_fields=['status', 'process_error', 'updated_at'])


def enqueue_ar_asset_build(asset_id: int) -> str | None:
    """Queue processing. Never run rembg inside the HTTP request."""
    try:
        result = build_ar_asset.delay(asset_id)
        return str(result.id)
    except Exception as err:
        logger.warning('Celery unavailable for AR asset %s: %s', asset_id, err)
        return None
