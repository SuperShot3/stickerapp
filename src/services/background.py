"""Local background removal via rembg (requires: pip install \"rembg[cpu]\")"""

from __future__ import annotations

import io
import logging

from PIL import Image

from src.config import REMOVE_BG_ENABLED

logger = logging.getLogger(__name__)

_rembg_remove = None
_rembg_checked = False


class BackgroundRemovalUnavailable(Exception):
    """rembg/onnxruntime missing or background removal failed."""


def _load_rembg():
    global _rembg_remove, _rembg_checked
    if _rembg_checked:
        return _rembg_remove
    _rembg_checked = True
    try:
        from rembg import remove as rembg_remove

        _rembg_remove = rembg_remove
    except ImportError as exc:
        logger.warning("rembg not installed: %s", exc)
    return _rembg_remove


def background_removal_available() -> bool:
    if not REMOVE_BG_ENABLED:
        return False
    return _load_rembg() is not None


def remove_background(image_bytes: bytes) -> bytes:
    if not REMOVE_BG_ENABLED:
        return image_bytes

    rembg_remove = _load_rembg()
    if rembg_remove is None:
        raise BackgroundRemovalUnavailable(
            'Background removal is enabled but rembg is not installed. '
            'Run: pip install "rembg[cpu]"'
        )

    try:
        result = rembg_remove(image_bytes)
        if isinstance(result, bytes):
            return result
        return bytes(result)
    except Exception as exc:
        logger.exception("Background removal failed")
        raise BackgroundRemovalUnavailable(
            f"Background removal failed: {exc}"
        ) from exc


def _transparent_pixel_ratio(img: Image.Image) -> float:
    """Share of pixels that are mostly transparent (background removed)."""
    alpha = img.split()[3]
    data = alpha.get_flattened_data()
    if not data:
        return 0.0
    transparent = sum(1 for p in data if p < 48)
    return transparent / len(data)


def validate_cutout(img: Image.Image) -> None:
    """Fail fast if the image still looks like a full photo with background."""
    ratio = _transparent_pixel_ratio(img)
    if ratio < 0.18:
        raise BackgroundRemovalUnavailable(
            "Background was not removed (cutout has almost no transparency). "
            "Restart the bot after: pip install \"rembg[cpu]\""
        )

    w, h = img.size
    alpha = img.split()[3]
    corners = (
        alpha.getpixel((0, 0)),
        alpha.getpixel((w - 1, 0)),
        alpha.getpixel((0, h - 1)),
        alpha.getpixel((w - 1, h - 1)),
    )
    if sum(1 for p in corners if p > 200) >= 3:
        raise BackgroundRemovalUnavailable(
            "Background was not removed (image corners are still solid)."
        )


def _max_side_for_scale(scale_percent: int) -> int:
    """Telegram stickers are 512×512; scale_percent 100 ≈ 480px subject max side."""
    scale_percent = max(50, min(150, scale_percent))
    return max(240, min(504, int(480 * scale_percent / 100)))


def fit_rgba_to_sticker_canvas(
    image_bytes: bytes,
    *,
    validate: bool = True,
    scale_percent: int = 100,
) -> Image.Image:
    """Scale RGBA cutout and center on 512×512 transparent canvas."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    max_side = _max_side_for_scale(scale_percent)
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    x = (512 - img.width) // 2
    y = (512 - img.height) // 2
    canvas.paste(img, (x, y), img)
    if validate:
        validate_cutout(canvas)
    return canvas


def scale_cutout_on_canvas(cutout: Image.Image, scale_percent: int) -> Image.Image:
    """Re-fit an existing 512×512 cutout larger or smaller (50–150%)."""
    img = cutout.convert("RGBA")
    alpha = img.split()[3]
    bbox = alpha.getbbox()
    if not bbox:
        return img

    subject = img.crop(bbox)
    max_side = _max_side_for_scale(scale_percent)
    subject.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    x = (512 - subject.width) // 2
    y = (512 - subject.height) // 2
    canvas.paste(subject, (x, y), subject)
    return canvas


def prepare_sticker_canvas(image_bytes: bytes) -> Image.Image:
    """Cut out background and fit on 512×512 transparent canvas."""
    cutout_bytes = remove_background(image_bytes)
    return fit_rgba_to_sticker_canvas(cutout_bytes)
