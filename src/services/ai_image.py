"""OpenAI image edit — background removal fallback only (not product re-generation)."""

from __future__ import annotations

import base64
import io
import json
import logging

import aiohttp
from PIL import Image

from src.config import (
    AI_API_BASE,
    AI_API_KEY,
    AI_BG_FALLBACK_ENABLED,
    AI_EDIT_PROMPT,
    AI_IMAGE_MODEL,
)
from src.services.api_usage import ApiUsageSnapshot, snapshot_from_openai_usage

logger = logging.getLogger(__name__)

# Strict: cut out only — no relighting, sharpening, or re-drawing the product.
DEFAULT_BG_REMOVAL_PROMPT = (
    "Remove the background only. Keep the main subject exactly as in the original photo: "
    "same colors, lighting, textures, shape, and details. Do not enhance, retouch, "
    "recolor, or redraw anything. Output only the subject on a fully transparent "
    "background with clean edges. No new objects, text, shadows on a floor, or backdrop."
)


class AiImageError(Exception):
    """OpenAI background-removal fallback failed."""


def ai_bg_fallback_enabled() -> bool:
    return bool(AI_API_KEY) and AI_BG_FALLBACK_ENABLED


def _ensure_png_bytes(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _download_image_url(session: aiohttp.ClientSession, url: str) -> bytes:
    async with session.get(url) as resp:
        if resp.status >= 400:
            raise AiImageError(f"Failed to download OpenAI image ({resp.status}).")
        return await resp.read()


async def _parse_edit_response(
    session: aiohttp.ClientSession, payload: dict
) -> bytes:
    data = payload.get("data")
    if not data:
        raise AiImageError("OpenAI returned no image data.")

    item = data[0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])

    url = item.get("url")
    if not url:
        raise AiImageError("OpenAI response missing image bytes and URL.")

    return await _download_image_url(session, url)


async def remove_background_openai(
    image_bytes: bytes,
) -> tuple[bytes, ApiUsageSnapshot | None]:
    """
    Last-resort BG removal via OpenAI /images/edits (transparent background).
    Prefer rembg or remove.bg for faithful cutouts.
    """
    if not AI_API_KEY:
        raise AiImageError("AI_API_KEY is not set.")

    png_bytes = _ensure_png_bytes(image_bytes)
    url = f"{AI_API_BASE}/images/edits"
    prompt = AI_EDIT_PROMPT or DEFAULT_BG_REMOVAL_PROMPT

    form = aiohttp.FormData()
    form.add_field("model", AI_IMAGE_MODEL)
    form.add_field("prompt", prompt)
    form.add_field("background", "transparent")
    form.add_field("output_format", "png")
    form.add_field("input_fidelity", "high")
    form.add_field("size", "1024x1024")
    form.add_field(
        "image",
        png_bytes,
        filename="input.png",
        content_type="image/png",
    )

    headers = {"Authorization": f"Bearer {AI_API_KEY}"}
    timeout = aiohttp.ClientTimeout(total=180)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, data=form, headers=headers) as resp:
            body = await resp.read()
            if resp.status >= 400:
                detail = body.decode("utf-8", errors="replace")[:500]
                try:
                    err = json.loads(body).get("error", {})
                    msg = err.get("message") or detail
                except (json.JSONDecodeError, AttributeError):
                    msg = detail
                raise AiImageError(f"OpenAI API error ({resp.status}): {msg}")

            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise AiImageError("OpenAI returned invalid JSON.") from exc

            result = await _parse_edit_response(session, payload)
            usage = snapshot_from_openai_usage(
                payload.get("usage"), model=AI_IMAGE_MODEL
            )

    Image.open(io.BytesIO(result)).verify()
    return result, usage
