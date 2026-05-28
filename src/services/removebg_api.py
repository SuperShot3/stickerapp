"""remove.bg API — dedicated background removal (optional)."""

from __future__ import annotations

import logging

import aiohttp

from src.config import REMOVE_BG_API_KEY
from src.services.api_usage import ApiUsageSnapshot, snapshot_from_removebg

logger = logging.getLogger(__name__)

REMOVEBG_URL = "https://api.remove.bg/v1.0/removebg"


class RemoveBgApiError(Exception):
    """remove.bg request failed."""


def removebg_api_available() -> bool:
    return bool(REMOVE_BG_API_KEY)


def _parse_removebg_credits(headers) -> float | None:
    raw = headers.get("X-Credits-Charged") or headers.get("x-credits-charged")
    if raw is None:
        return 1.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


async def remove_background_api(
    image_bytes: bytes,
) -> tuple[bytes, ApiUsageSnapshot | None]:
    """Return PNG with transparent background."""
    if not REMOVE_BG_API_KEY:
        raise RemoveBgApiError("REMOVE_BG_API_KEY is not set.")

    form = aiohttp.FormData()
    form.add_field("size", "auto")
    form.add_field("format", "png")
    form.add_field(
        "image_file",
        image_bytes,
        filename="photo.jpg",
        content_type="application/octet-stream",
    )

    headers = {"X-Api-Key": REMOVE_BG_API_KEY}
    timeout = aiohttp.ClientTimeout(total=120)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(REMOVEBG_URL, data=form, headers=headers) as resp:
            body = await resp.read()
            if resp.status >= 400:
                detail = body.decode("utf-8", errors="replace")[:400]
                raise RemoveBgApiError(
                    f"remove.bg error ({resp.status}): {detail}"
                )
            usage = snapshot_from_removebg(_parse_removebg_credits(resp.headers))
            return body, usage
