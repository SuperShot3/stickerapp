"""

Sticker pipeline: remove background (rembg → remove.bg → OpenAI) → apply glow.

"""



from __future__ import annotations



import asyncio

import logging

from pathlib import Path



from PIL import Image



from src.config import REMOVE_BG_ENABLED, ROOT

from src.services.ai_image import AiImageError, ai_bg_fallback_enabled, remove_background_openai
from src.services.api_usage import record_api_usage

from src.services.background import (
    BackgroundRemovalUnavailable,
    background_removal_available,
    fit_rgba_to_sticker_canvas,
    prepare_sticker_canvas,
    scale_cutout_on_canvas,
)

from src.services.glow import apply_glow

from src.services.removebg_api import RemoveBgApiError, remove_background_api, removebg_api_available



logger = logging.getLogger(__name__)



OUTPUT_DIR = ROOT / "data" / "generations"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)





def cutout_path_for_job(job_id: int) -> Path:

    return OUTPUT_DIR / f"job_{job_id}_cutout.png"





def _bg_removal_options_available() -> bool:

    return (

        (REMOVE_BG_ENABLED and background_removal_available())

        or removebg_api_available()

        or ai_bg_fallback_enabled()

    )





async def _try_rembg(source_bytes: bytes) -> Image.Image | None:

    if not REMOVE_BG_ENABLED or not background_removal_available():

        return None

    try:

        return await asyncio.to_thread(prepare_sticker_canvas, source_bytes)

    except BackgroundRemovalUnavailable as exc:

        logger.warning("rembg cutout failed: %s", exc)

        return None





async def _try_removebg_api(
    source_bytes: bytes, job_id: int | None = None
) -> Image.Image | None:

    if not removebg_api_available():

        return None

    try:

        logger.info("Trying remove.bg API for background removal…")

        cutout_bytes, usage = await remove_background_api(source_bytes)
        await record_api_usage(job_id, usage)

        return await asyncio.to_thread(fit_rgba_to_sticker_canvas, cutout_bytes)

    except RemoveBgApiError as exc:

        logger.warning("remove.bg failed: %s", exc)

        return None





async def _try_openai_bg(
    source_bytes: bytes, job_id: int | None = None
) -> Image.Image | None:

    if not ai_bg_fallback_enabled():

        return None

    try:

        logger.info("Trying OpenAI background-removal fallback…")

        cutout_bytes, usage = await remove_background_openai(source_bytes)
        await record_api_usage(job_id, usage)

        return await asyncio.to_thread(fit_rgba_to_sticker_canvas, cutout_bytes)

    except AiImageError as exc:

        logger.warning("OpenAI BG fallback failed: %s", exc)

        return None





def quality_bg_removal_available() -> bool:
    return removebg_api_available() or ai_bg_fallback_enabled()


async def save_cutout(
    job_id: int,
    source_bytes: bytes,
    *,
    quality_first: bool = False,
) -> Image.Image:
    """Remove background and cache subject cutout. rembg first, then optional APIs."""

    if not _bg_removal_options_available():
        raise BackgroundRemovalUnavailable(
            "No background removal available. Install rembg: pip install \"rembg[cpu]\" "
            "or set REMOVE_BG_API_KEY / AI_API_KEY in .env."
        )

    cutout_path = cutout_path_for_job(job_id)
    cutout_path.unlink(missing_ok=True)

    if quality_first and quality_bg_removal_available():
        logger.info("Job %s: high-quality background removal (API first)…", job_id)
        cutout = await _try_removebg_api(source_bytes, job_id)
        if cutout is None:
            cutout = await _try_openai_bg(source_bytes, job_id)
        if cutout is None:
            cutout = await _try_rembg(source_bytes)
    else:
        logger.info("Job %s: removing background (rembg first)…", job_id)
        cutout = await _try_rembg(source_bytes)
        if cutout is None:
            cutout = await _try_removebg_api(source_bytes, job_id)
        if cutout is None:
            cutout = await _try_openai_bg(source_bytes, job_id)

    if cutout is None:
        raise BackgroundRemovalUnavailable(
            "Could not remove the background. Use a clearer photo with one main subject, "
            "or add REMOVE_BG_API_KEY (remove.bg) for harder images."
        )

    cutout.save(cutout_path, "PNG")
    logger.info("Job %s: cutout saved (%s)", job_id, cutout_path.name)
    return cutout





def render_glow_variants(
    job_id: int,
    glow_color: str,
    *,
    outline_width: int = 2,
    glow_strength: int = 55,
    subject_scale: int = 100,
) -> list[Path]:
    """One sticker PNG: cutout with glow at the chosen strength."""

    path = cutout_path_for_job(job_id)
    if not path.is_file():
        raise FileNotFoundError(f"Cutout missing for job {job_id}")

    cutout = Image.open(path).convert("RGBA")
    if subject_scale != 100:
        cutout = scale_cutout_on_canvas(cutout, subject_scale)

    sticker = apply_glow(
        cutout,
        glow_color,
        glow_strength=glow_strength,
        outline_width=outline_width,
    )

    out = OUTPUT_DIR / f"job_{job_id}_v1.png"

    sticker.save(out, "PNG")

    return [out]





async def generate_variations(
    job_id: int,
    glow_color: str,
    source_bytes: bytes,
    *,
    outline_width: int = 2,
    glow_strength: int = 55,
    subject_scale: int = 100,
) -> list[Path]:
    await save_cutout(job_id, source_bytes)
    return render_glow_variants(
        job_id,
        glow_color,
        outline_width=outline_width,
        glow_strength=glow_strength,
        subject_scale=subject_scale,
    )


