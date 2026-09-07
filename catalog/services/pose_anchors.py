"""Body-pose shoulder anchors for AR calibration.

Uses Ultralytics YOLO-pose (COCO 17 keypoints) when available. MediaPipe is
intentionally avoided: its macOS Metal path aborts the whole Celery worker
process (FATAL Check failed), which is unacceptable for a background queue.

Falls back to None → silhouette estimator in ar_assets.estimate_anchors.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from io import BytesIO
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

# COCO / YOLO-pose keypoint indices
_L_SHOULDER = 5
_R_SHOULDER = 6
_L_HIP = 11
_R_HIP = 12


@lru_cache(maxsize=1)
def _yolo_pose_model() -> Any | None:
    try:
        from ultralytics import YOLO
    except ImportError as err:
        logger.warning('ultralytics not installed — pose anchors disabled: %s', err)
        return None
    try:
        from pathlib import Path

        # Keep weights under the app tree, not the process CWD.
        weights = Path(__file__).resolve().parent.parent / 'ml_models' / 'yolo11n-pose.pt'
        weights.parent.mkdir(parents=True, exist_ok=True)
        model = YOLO(str(weights) if weights.exists() else 'yolo11n-pose.pt')
        # Persist download next to the app if Ultralytics pulled the hub weight.
        if not weights.exists():
            hub = Path('yolo11n-pose.pt')
            if hub.exists():
                hub.replace(weights)
                model = YOLO(str(weights))
        logger.info('Loaded YOLO pose model %s', weights if weights.exists() else 'yolo11n-pose.pt')
        return model
    except Exception as err:
        logger.warning('Could not load YOLO pose model: %s', err)
        return None


def detect_body_anchors(raw_bytes: bytes) -> dict | None:
    """
    Detect shoulders (and hips) on a catalog photo that includes a person.

    Returns normalized coords in image space, or None when no reliable pose
    is found (flat-lay garment, empty cutout, etc.).
    """
    model = _yolo_pose_model()
    if model is None:
        return None

    try:
        import numpy as np

        img = Image.open(BytesIO(raw_bytes)).convert('RGB')
        rgb = np.asarray(img)
        results = model.predict(
            source=rgb,
            verbose=False,
            conf=0.35,
            imgsz=640,
            device='cpu',
            max_det=1,
        )
    except Exception as err:
        logger.warning('YOLO pose failed: %s', err)
        return None

    if not results:
        return None
    result = results[0]
    if result.keypoints is None or result.keypoints.data is None:
        return None

    kps = result.keypoints.data
    if kps.shape[0] < 1 or kps.shape[1] <= _R_HIP:
        return None

    person = kps[0].cpu().numpy()  # [17, 3] → x, y, conf (pixel coords)
    width, height = img.size

    def point(index: int) -> tuple[float, float, float]:
        x, y, conf = float(person[index][0]), float(person[index][1]), float(person[index][2])
        return x / max(width, 1), y / max(height, 1), conf

    ls_x, ls_y, ls_c = point(_L_SHOULDER)
    rs_x, rs_y, rs_c = point(_R_SHOULDER)
    lh_x, lh_y, lh_c = point(_L_HIP)
    rh_x, rh_y, rh_c = point(_R_HIP)

    if ls_c < 0.40 or rs_c < 0.40:
        return None

    # Image-left / image-right (not anatomical) so it matches garment PNG left→right.
    if ls_x <= rs_x:
        left, right = (ls_x, ls_y), (rs_x, rs_y)
    else:
        left, right = (rs_x, rs_y), (ls_x, ls_y)

    if lh_x <= rh_x:
        hip_l, hip_r = (lh_x, lh_y), (rh_x, rh_y)
    else:
        hip_l, hip_r = (rh_x, rh_y), (lh_x, lh_y)

    span = abs(right[0] - left[0])
    if span < 0.05:
        return None

    tilt = abs(right[1] - left[1]) / max(span, 1e-3)
    if tilt > 0.45:
        return None

    logger.info(
        'YOLO-pose shoulders L=(%.3f,%.3f) R=(%.3f,%.3f) span=%.3f tilt=%.3f',
        left[0], left[1], right[0], right[1], span, tilt,
    )

    return {
        'anchor_left': {'x': float(left[0]), 'y': float(left[1])},
        'anchor_right': {'x': float(right[0]), 'y': float(right[1])},
        'hip_left': {'x': float(hip_l[0]), 'y': float(hip_l[1])},
        'hip_right': {'x': float(hip_r[0]), 'y': float(hip_r[1])},
        'shoulder_span': float(span),
        'source': 'yolo_pose',
    }


def remap_pose_to_cutout(
    pose: dict,
    *,
    src_w: int,
    src_h: int,
    crop_box: tuple[int, int, int, int],
) -> dict:
    """
    Map pose normalized coords from the full source into the trimmed cutout PNG.

    crop_box is PIL getbbox() style (left, top, right, bottom) in source pixels.
    """
    left, top, right, bottom = crop_box
    crop_w = max(right - left, 1)
    crop_h = max(bottom - top, 1)

    def remap(pt: dict) -> dict:
        px = pt['x'] * src_w
        py = pt['y'] * src_h
        return {
            'x': min(max((px - left) / crop_w, 0.0), 1.0),
            'y': min(max((py - top) / crop_h, 0.0), 1.0),
        }

    return {
        'anchor_left': remap(pose['anchor_left']),
        'anchor_right': remap(pose['anchor_right']),
        'hip_left': remap(pose['hip_left']),
        'hip_right': remap(pose['hip_right']),
        'source': pose.get('source', 'yolo_pose'),
    }
