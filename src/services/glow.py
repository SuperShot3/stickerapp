"""Cutout + glow: the core StickerNow look."""

from __future__ import annotations

from PIL import Image, ImageChops, ImageFilter

# RGB glow colors
GLOW_COLORS: dict[str, tuple[int, int, int]] = {
    "cyan": (0, 255, 255),
    "pink": (255, 100, 220),
    "gold": (255, 200, 50),
    "white": (255, 255, 255),
    "purple": (180, 80, 255),
}


def apply_glow(
    cutout: Image.Image,
    color_key: str,
    glow_strength: int,
    outline_width: int,
) -> Image.Image:
    """
    Apply neon glow + optional outline around the subject alpha.
    cutout: RGBA 512×512, transparent background.
    """
    color = GLOW_COLORS.get(color_key, GLOW_COLORS["cyan"])
    strength = max(0, min(100, glow_strength))
    outline = max(0, min(12, outline_width))

    base = cutout.convert("RGBA")
    if strength == 0 and outline == 0:
        return base

    alpha = base.split()[3]
    size = base.size

    # Soft outer glow (blurred colored silhouette)
    glow_layer = Image.new("RGBA", size, (*color, 0))
    if strength > 0:
        silhouette = Image.new("RGBA", size, (*color, 255))
        silhouette.putalpha(alpha)
        blur_radius = max(2, int(3 + strength * 0.45))
        blurred = silhouette.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        br, bg, bb, ba = blurred.split()
        ba = ba.point(lambda p: min(255, int(p * (strength / 85))) if p else 0)
        glow_layer = Image.merge("RGBA", (br, bg, bb, ba))

    result = Image.alpha_composite(glow_layer, base)

    # Crisp outline ring around the subject
    if outline > 0:
        k = outline * 2 + 1
        dilated = alpha.filter(ImageFilter.MaxFilter(k))
        ring = ImageChops.subtract(dilated, alpha)
        ring = ring.point(lambda p: 255 if p > 20 else 0)
        outline_layer = Image.new("RGBA", size, (*color, 255))
        outline_layer.putalpha(ring)
        result = Image.alpha_composite(result, outline_layer)

    return result
