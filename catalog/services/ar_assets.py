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

MAX_SIDE_PX = 4096
MIN_WIDTH_PX = 512


def validate_ar_upload(upload: BinaryIO) -> BinaryIO:
    max_mb = getattr(settings, 'AR_ASSET_UPLOAD_MAX_MB', 8)
    size = getattr(upload, 'size', None)
    if size is not None and size > max_mb * 1024 * 1024:
        raise ValidationError(f'Máximo {max_mb} MB.')

    try:
        raw = upload.read()
        upload.seek(0)
    except Exception as err:
        raise ValidationError('No se pudo leer el archivo.') from err

    if not raw:
        raise ValidationError('El archivo está vacío.')

    try:
        img = Image.open(BytesIO(raw))
        img.load()
    except Exception as err:
        raise ValidationError('Archivo de imagen inválido.') from err

    # Too-small images are accepted; _trim_and_normalize will upscale them.
    if img.width > MAX_SIDE_PX or img.height > MAX_SIDE_PX:
        raise ValidationError(f'Máximo {MAX_SIDE_PX} px por lado.')

    if is_placeholder_overlay(raw):
        raise ValidationError(
            'La imagen parece un placeholder gris/uniforme. Sube una foto real de la prenda '
            '(mín. 512 px, con la silueta visible).',
        )

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


def _trim_and_normalize(img: Image.Image) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Crop transparent padding, then scale to [MIN_WIDTH_PX, AR_ASSET_MAX_WIDTH].

    Returns (image, crop_box) where crop_box is the alpha bbox in the
    pre-scale canvas (left, top, right, bottom).
    """
    max_width = getattr(settings, 'AR_ASSET_MAX_WIDTH', 1024)
    bbox = img.getbbox() or (0, 0, img.width, img.height)
    img = img.crop(bbox)

    # Downscale oversized images.
    if img.width > max_width:
        height = max(1, round(img.height * (max_width / img.width)))
        img = img.resize((max_width, height), Image.Resampling.LANCZOS)
    # Upscale images that are too small — rembg and anchor estimation need
    # enough pixels to detect the garment silhouette reliably.
    elif img.width < MIN_WIDTH_PX and img.width > 0:
        scale = MIN_WIDTH_PX / img.width
        height = max(1, round(img.height * scale))
        logger.info(
            'Upscaling AR image from %dx%d to %dx%d',
            img.width,
            img.height,
            MIN_WIDTH_PX,
            height,
        )
        img = img.resize((MIN_WIDTH_PX, height), Image.Resampling.LANCZOS)
    return img, bbox


def estimate_anchors(img: Image.Image, pose_hint: dict | None = None) -> AnchorConfig:
    """Estimate shoulder/hip anchors from silhouette, optionally seeded by MediaPipe pose."""
    import numpy as np

    # Prefer MediaPipe shoulders when they land inside the opaque garment silhouette.
    if pose_hint and pose_hint.get('anchor_left') and pose_hint.get('anchor_right'):
        alpha = np.array(img.getchannel('A'))
        height, width = alpha.shape
        mask = alpha > 20
        al = pose_hint['anchor_left']
        ar = pose_hint['anchor_right']
        lx = int(round(al['x'] * (width - 1)))
        ly = int(round(al['y'] * (height - 1)))
        rx = int(round(ar['x'] * (width - 1)))
        ry = int(round(ar['y'] * (height - 1)))

        def near_opaque(x: int, y: int, radius: int = 8) -> bool:
            y0, y1 = max(0, y - radius), min(height, y + radius + 1)
            x0, x1 = max(0, x - radius), min(width, x + radius + 1)
            return bool(mask[y0:y1, x0:x1].any())

        if near_opaque(lx, ly) and near_opaque(rx, ry):
            span = max(abs(rx - lx), 1)
            rows = np.where(mask.any(axis=1))[0]
            top = int(rows[0]) if rows.size else 0
            collar_height = (min(ly, ry) - top) / span
            offset_y = round(max(-0.50, min(0.30, collar_height - 0.10)), 3)
            aspect = height / max(width, 1)
            body_part = 'TORSO' if aspect < 1.5 else ('FULL_BODY' if aspect < 2.2 else 'LEGS')
            logger.info('AR anchors from YOLO-pose (offset_y=%.3f)', offset_y)
            return validate_anchor_config({
                'version': 1,
                'anchor_left': {'x': float(al['x']), 'y': float(al['y'])},
                'anchor_right': {'x': float(ar['x']), 'y': float(ar['y'])},
                'offset_y': offset_y,
                'body_part': body_part,
                'auto_calibrated': True,
            })

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
    shoulder_span_px = max(right_x - left_x, 1)
    inset = shoulder_span_px * 0.08
    left_norm = min(max((left_x + inset) / width, 0.0), 1.0)
    right_norm = min(max((right_x - inset) / width, 0.0), 1.0)
    shoulder_y_norm = shoulder_row / height

    collar_height = (shoulder_row - int(rows[0])) / shoulder_span_px
    offset_y = round(max(-0.50, min(0.30, collar_height - 0.10)), 3)

    aspect = height / max(width, 1)
    if aspect < 1.5:
        body_part = 'TORSO'
    elif aspect < 2.2:
        body_part = 'FULL_BODY'
    else:
        body_part = 'LEGS'

    return validate_anchor_config({
        'version': 1,
        'anchor_left': {'x': left_norm, 'y': shoulder_y_norm},
        'anchor_right': {'x': right_norm, 'y': shoulder_y_norm},
        'offset_y': offset_y,
        'body_part': body_part,
        'auto_calibrated': True,
    })


def _knockout_light_background(raw_bytes: bytes) -> bytes:
    """Fallback when rembg is not installed: fade near-white catalog backdrops."""
    img = Image.open(BytesIO(raw_bytes)).convert('RGBA')
    pixels = img.load()
    width, height = img.size
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            luma = 0.299 * red + 0.587 * green + 0.114 * blue
            if luma >= 245 and abs(red - green) < 18 and abs(green - blue) < 18:
                pixels[x, y] = (red, green, blue, 0)
            elif luma >= 230:
                fade = int(alpha * ((245 - luma) / 15))
                pixels[x, y] = (red, green, blue, max(0, fade))
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def _opaque_ratio(png_bytes: bytes) -> float:
    img = Image.open(BytesIO(png_bytes)).convert('RGBA')
    alpha = img.getchannel('A')
    # extrema is cheap; histogram gives a real ratio
    hist = alpha.histogram()
    opaque = sum(hist[21:])  # alpha > 20
    total = max(sum(hist), 1)
    return opaque / total


def _remove_background(raw_bytes: bytes) -> bytes:
    try:
        from rembg import new_session, remove
    except ImportError as err:
        logger.warning('rembg no instalado; usando recorte por umbral: %s', err)
        return _knockout_light_background(raw_bytes)

    # u2net_cloth_seg often returns empty/tall garbage on catalog photos.
    # Prefer general u2net; keep cloth_seg as a secondary attempt.
    preferred = getattr(settings, 'AR_REMBG_MODEL', 'u2net')
    models = [preferred, 'u2net', 'u2net_cloth_seg']
    use_matting = getattr(settings, 'AR_REMBG_ALPHA_MATTING', False)
    last_err: Exception | None = None
    best: bytes | None = None
    best_ratio = -1.0

    for model in dict.fromkeys(models):
        try:
            session = new_session(model)
            out = remove(raw_bytes, session=session, alpha_matting=use_matting)
            ratio = _opaque_ratio(out)
            logger.info('AR rembg model=%s opaque_ratio=%.3f', model, ratio)
            if ratio > best_ratio:
                best = out
                best_ratio = ratio
            # Good enough cutout — keep it.
            if 0.05 <= ratio <= 0.98:
                return out
        except Exception as err:
            last_err = err
            logger.warning('AR rembg model %s failed: %s', model, err)

    if best is not None and best_ratio >= 0.05:
        return best

    logger.warning(
        'AR rembg produced empty/unusable cutout (best_ratio=%.3f, err=%s); '
        'falling back to threshold knockout',
        best_ratio,
        last_err,
    )
    return _knockout_light_background(raw_bytes)


def is_placeholder_overlay(raw_bytes: bytes) -> bool:
    """Seed squares are tiny uniform RGB images, not wearable cutouts."""
    if not raw_bytes or len(raw_bytes) < 256:
        return True
    try:
        img = Image.open(BytesIO(raw_bytes))
        img.load()
    except Exception:
        return True
    # Seed demo uses a solid (220,220,220) square — one unique color.
    extrema = img.convert('RGB').getextrema()
    return all(lo == hi for lo, hi in extrema)


def copy_catalog_image_as_source(asset) -> bool:
    """Use the product photo as rembg input when the admin never uploaded one."""
    from pathlib import Path

    from catalog.services.media_cleanup import delete_field_file

    images = list(asset.product.images.all())
    photo = None
    if asset.color_id:
        photo = next((item for item in images if item.color_id == asset.color_id), None)
    photo = photo or (images[0] if images else None)
    if photo is None or not photo.image:
        return False

    try:
        path = Path(photo.image.path)
    except Exception:
        return False
    if not path.exists():
        logger.warning('Catalog image missing on disk: %s', path)
        return False

    payload = path.read_bytes()
    if not payload:
        return False

    if asset.source_image:
        delete_field_file(asset.source_image)

    name = path.name
    asset.source_image.save(name, ContentFile(payload), save=False)
    return True


def process_garment_image(raw_bytes: bytes) -> tuple[bytes, AnchorConfig]:
    """Cut out background when possible and estimate anchors. Returns (png, config)."""
    from catalog.services.pose_anchors import detect_body_anchors, remap_pose_to_cutout

    # Pose on the ORIGINAL catalog photo (person + garment) — highest accuracy.
    orig = Image.open(BytesIO(raw_bytes)).convert('RGB')
    pose_raw = detect_body_anchors(raw_bytes)
    pose_size = orig.size

    data = raw_bytes
    if getattr(settings, 'AR_AUTO_CUTOUT', True):
        try:
            data = _remove_background(raw_bytes)
        except Exception as err:
            logger.warning('AR cutout skipped: %s', err)

    img = Image.open(BytesIO(data)).convert('RGBA')

    # If rembg changed canvas size, re-detect on the cutout composite.
    if pose_raw is not None and img.size != pose_size:
        pose_raw = detect_body_anchors(_rgba_to_jpeg_bytes(img))
        pose_size = img.size
    elif pose_raw is None:
        pose_raw = detect_body_anchors(_rgba_to_jpeg_bytes(img))
        pose_size = img.size

    src_w, src_h = img.size
    img, crop_box = _trim_and_normalize(img)

    pose_hint = None
    if pose_raw is not None and pose_size == (src_w, src_h):
        pose_hint = remap_pose_to_cutout(
            pose_raw,
            src_w=src_w,
            src_h=src_h,
            crop_box=crop_box,
        )

    anchor = estimate_anchors(img, pose_hint=pose_hint)
    buf = BytesIO()
    img.save(buf, format='PNG', optimize=True)
    return buf.getvalue(), anchor


def _rgba_to_jpeg_bytes(img: Image.Image) -> bytes:
    """Composite RGBA onto white for MediaPipe (expects opaque RGB)."""
    rgb = Image.new('RGB', img.size, (255, 255, 255))
    rgb.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
    buf = BytesIO()
    rgb.save(buf, format='JPEG', quality=92)
    return buf.getvalue()


def apply_processed_bytes(*, asset, png: bytes, anchor: AnchorConfig) -> None:
    from catalog.models import _ascii_slug

    img = Image.open(BytesIO(png))
    raw_slug = asset.color.slug if asset.color_id else 'default'
    color_slug = _ascii_slug(raw_slug)
    old_name: str | None = asset.file.name if asset.file else None
    # Write new file first — if this fails, the old file is untouched.
    asset.file.save(f'{color_slug}.png', ContentFile(png), save=False)
    # Remove stale file only when the path actually changed (e.g. Unicode → ASCII).
    if old_name and old_name != asset.file.name:
        try:
            if asset.file.storage.exists(old_name):
                asset.file.storage.delete(old_name)
        except Exception:
            logger.warning('Could not delete old AR file %s', old_name)
    previous = asset.anchor_config if isinstance(asset.anchor_config, dict) else {}
    merged = dict(anchor)
    if previous.get('auto_calibrated') is False:
        if 'width_factor' in previous:
            merged['width_factor'] = previous['width_factor']
        if 'offset_y' in previous:
            merged['offset_y'] = previous['offset_y']
        if isinstance(previous.get('size_scale'), dict):
            merged['size_scale'] = previous['size_scale']
        merged['auto_calibrated'] = False
    asset.anchor_config = merged
    asset.width = img.width
    asset.height = img.height
    asset.status = asset.READY
    asset.process_error = ''
