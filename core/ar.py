"""Versioned AR overlay contract shared by catalog services and the mobile client."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

ANCHOR_CONFIG_VERSION = 1
BODY_PARTS = frozenset({'TORSO', 'LEGS', 'FULL_BODY'})
DEFAULT_SIZE_SCALE: dict[str, float] = {
    'XS': 0.90,
    'S': 0.95,
    'M': 1.0,
    'L': 1.06,
    'XL': 1.12,
    'XXL': 1.18,
}

BodyPart = Literal['TORSO', 'LEGS', 'FULL_BODY']


class AnchorPoint(TypedDict):
    x: float
    y: float


class AnchorConfig(TypedDict):
    version: int
    anchor_left: AnchorPoint
    anchor_right: AnchorPoint
    offset_y: float
    size_scale: dict[str, float]
    body_part: BodyPart
    auto_calibrated: bool


def default_anchor_config(*, body_part: BodyPart = 'TORSO', auto_calibrated: bool = True) -> AnchorConfig:
    return {
        'version': ANCHOR_CONFIG_VERSION,
        'anchor_left': {'x': 0.18, 'y': 0.115},
        'anchor_right': {'x': 0.82, 'y': 0.115},
        'offset_y': -0.02,
        'size_scale': dict(DEFAULT_SIZE_SCALE),
        'body_part': body_part,
        'auto_calibrated': auto_calibrated,
    }


def _as_point(value: Any, field: str) -> AnchorPoint:
    if not isinstance(value, dict):
        raise ValueError(f'{field} debe ser un objeto {{x, y}}')
    try:
        x = float(value['x'])
        y = float(value['y'])
    except (KeyError, TypeError, ValueError) as err:
        raise ValueError(f'{field} requiere x e y numéricos') from err
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        raise ValueError(f'{field} debe estar normalizado en [0, 1]')
    return {'x': round(x, 4), 'y': round(y, 4)}


def validate_anchor_config(raw: Any) -> AnchorConfig:
    """Validate and normalize a v1 `anchor_config`. Raises ValueError if malformed."""
    if not isinstance(raw, dict):
        raise ValueError('anchor_config debe ser un objeto JSON')

    version = int(raw.get('version', ANCHOR_CONFIG_VERSION))
    if version != ANCHOR_CONFIG_VERSION:
        raise ValueError(f'version de anchor_config no soportada: {version}')

    body_part = str(raw.get('body_part', 'TORSO')).upper()
    if body_part not in BODY_PARTS:
        raise ValueError('body_part debe ser TORSO, LEGS o FULL_BODY')

    offset_y = float(raw.get('offset_y', -0.02))
    if not (-1.0 <= offset_y <= 1.0):
        raise ValueError('offset_y debe estar entre -1 y 1')

    size_raw = raw.get('size_scale') or DEFAULT_SIZE_SCALE
    if not isinstance(size_raw, dict) or not size_raw:
        raise ValueError('size_scale debe ser un objeto de códigos de talla')

    size_scale: dict[str, float] = {}
    for code, factor in size_raw.items():
        key = str(code).strip().upper()
        value = float(factor)
        if not key or value <= 0:
            raise ValueError(f'size_scale[{code}] inválido')
        size_scale[key] = round(value, 4)

    return {
        'version': ANCHOR_CONFIG_VERSION,
        'anchor_left': _as_point(raw.get('anchor_left'), 'anchor_left'),
        'anchor_right': _as_point(raw.get('anchor_right'), 'anchor_right'),
        'offset_y': round(offset_y, 4),
        'size_scale': size_scale,
        'body_part': body_part,  # type: ignore[typeddict-item]
        'auto_calibrated': bool(raw.get('auto_calibrated', False)),
    }
