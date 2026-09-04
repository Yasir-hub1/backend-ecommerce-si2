"""Celery tasks for catalog, including AR overlay processing."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def build_ar_asset(asset_id: int) -> None:
    from catalog.models import ARAsset
    from catalog.services.ar_assets import apply_processed_bytes, process_garment_image

    asset = ARAsset.objects.select_related('color').get(pk=asset_id)
    try:
        raw = asset.file.read()
        asset.file.seek(0)
        png, anchor = process_garment_image(raw)
        apply_processed_bytes(asset=asset, png=png, anchor=anchor)
        asset.save()
    except Exception as err:
        logger.exception('AR asset %s failed: %s', asset_id, err)
        asset.status = ARAsset.FAILED
        asset.process_error = str(err)[:300]
        asset.save(update_fields=['status', 'process_error', 'updated_at'])


def enqueue_ar_asset_build(asset_id: int) -> str | None:
    """Queue processing; run inline if the broker is unavailable (local/dev)."""
    try:
        result = build_ar_asset.delay(asset_id)
        return str(result.id)
    except Exception as err:
        logger.warning('Celery unavailable, processing AR asset inline: %s', err)
        build_ar_asset(asset_id)
        return None
