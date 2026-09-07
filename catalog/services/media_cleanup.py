"""Delete FieldFile contents from disk when DB rows go away or are replaced."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def delete_field_file(field_file: Any) -> None:
    """Remove a Django FieldFile from storage if it still exists on disk."""
    if field_file is None:
        return
    name = getattr(field_file, 'name', None) or ''
    if not name:
        return
    storage = getattr(field_file, 'storage', None)
    if storage is None:
        return
    try:
        if storage.exists(name):
            storage.delete(name)
            logger.info('Deleted media file %s', name)
    except Exception:
        logger.warning('Could not delete media file %s', name, exc_info=True)


def delete_product_image_files(image) -> None:
    delete_field_file(getattr(image, 'image', None))


def delete_ar_asset_files(asset) -> None:
    delete_field_file(getattr(asset, 'source_image', None))
    delete_field_file(getattr(asset, 'file', None))
