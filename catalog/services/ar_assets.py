"""Prepare overlay-2D garments: validate upload, cutout, estimate anchors."""

from __future__ import annotations

import logging
from io import BytesIO
from typing import BinaryIO

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image

from core.ar import AnchorConfig, default_anchor_config, validate_anchor_config

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MIN_SIDE_PX = 512


def validate_ar_upload(upload: BinaryIO) -> BinaryIO:
    max_mb = getattr(settings, 'AR_ASSET_UPLOAD_MAX_MB', 8)
    size = getattr(upload, 'size', None)
    if size is not None and size > max_mb * 1024 * 1024:
        raise ValidationError(f'Máximo {max_mb} MB.')

    try:
        img = Image.open(upload)
        img.verify()
    except Exception as err:
        raise ValidationError('Archivo de imagen inválido.') from err

    upload.seek(0)
    img = Image.open(upload)
    if min(img.size) < MIN_SIDE_PX:
        raise ValidationError(f'Mínimo {MIN_SIDE_PX} px en el lado menor.')

    auto_cutout = getattr(settings, 'AR_AUTO_CUTOUT', True)
    if img.mode in ('RGBA', 'LA'):
        if img.getchannel('A').getextrema()[0] == 255 and not auto_cutout:
            raise ValidationError('El PNG no tiene transparencia real.')
    elif not auto_cutout:
        raise ValidationError(
            'Sube un PNG con fondo transparente o activa el recorte automático.',
        )

    upload.seek(0)
    return upload


def _trim_and_normalize(img: Image.Image) -> Image.Image:
    max_width = getattr(settings, 'AR_ASSET_MAX_WIDTH', 1024)
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    if img.width > max_width:
        height = max(1, round(img.height * (max_width / img.width)))
        img = img.resize((max_width, height), Image.Resampling.LANCZOS)
    return img


def estimate_anchors(img: Image.Image) -> AnchorConfig:
    """Estimate shoulder/hip anchors from the garment silhouette."""
    import numpy as np

    alpha = np.array(img.getchannel('A'))
    height, width = alpha.shape
    mask = (alpha > 20).astype(np.uint8)
    rows = np.where(mask.any(axis=1))[0]
    if rows.size == 0:
        return default_anchor_config(auto_calibrated=True)

    top = int(rows[0])
    band = mask[top: top + max(1, int(height * 0.30))]
    widths = band.sum(axis=1)
    if widths.size == 0 or int(widths.max()) == 0:
        return default_anchor_config(auto_calibrated=True)

    shoulder_row = top + int(np.argmax(widths >= widths.max() * 0.92))
    cols = np.where(mask[shoulder_row] > 0)[0]
    if cols.size == 0:
        return default_anchor_config(auto_calibrated=True)

    left_x, right_x = int(cols[0]), int(cols[-1])
    inset = (right_x - left_x) * 0.08
    left_norm = min(max((left_x + inset) / width, 0.0), 1.0)
    right_norm = min(max((right_x - inset) / width, 0.0), 1.0)
    aspect = height / max(width, 1)
    if aspect < 1.5:
        body_part = 'TORSO'
    elif aspect < 2.2:
        body_part = 'FULL_BODY'
    else:
        body_part = 'LEGS'

    return validate_anchor_config({
        'version': 1,
        'anchor_left': {
            'x': left_norm,
            'y': shoulder_row / height,
        },
        'anchor_right': {
            'x': right_norm,
            'y': shoulder_row / height,
        },
        'offset_y': -0.02,
        'body_part': body_part,
        'auto_calibrated': True,
    })


def _remove_background(raw_bytes: bytes) -> bytes:
    from rembg import new_session, remove

    model = getattr(settings, 'AR_REMBG_MODEL', 'u2net_cloth_seg')
    session = new_session(model)
    return remove(raw_bytes, session=session, alpha_matting=True)


def process_garment_image(raw_bytes: bytes) -> tuple[bytes, AnchorConfig]:
    """Cut out background when possible and estimate anchors. Returns (png, config)."""
    data = raw_bytes
    if getattr(settings, 'AR_AUTO_CUTOUT', True):
        try:
            data = _remove_background(raw_bytes)
        except Exception as err:
            logger.warning('AR cutout skipped: %s', err)

    img = Image.open(BytesIO(data)).convert('RGBA')
    img = _trim_and_normalize(img)
    anchor = estimate_anchors(img)
    buf = BytesIO()
    img.save(buf, format='PNG', optimize=True)
    return buf.getvalue(), anchor


def apply_processed_bytes(*, asset, png: bytes, anchor: AnchorConfig) -> None:
    img = Image.open(BytesIO(png))
    color_slug = asset.color.slug if asset.color_id else 'default'
    asset.file.save(f'{color_slug}.png', ContentFile(png), save=False)
    asset.anchor_config = anchor
    asset.width = img.width
    asset.height = img.height
    asset.status = asset.READY
    asset.process_error = ''
