from __future__ import annotations

import json
import logging
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import (
    buy_packages_keyboard,
    edit_tune_keyboard,
    glow_color_keyboard,
    preview_keyboard,
)
from src.bot.states import StickerFlow
from src.config import PAYMENTS_ENABLED
from src.db.database import SessionLocal
from src.db.models import GenerationJob
from src.services.credits import add_credits, consume_credit, get_or_create_user
from src.services.background import BackgroundRemovalUnavailable
from src.services.removebg_api import removebg_api_available
from src.services.generation import (
    generate_variations,
    quality_bg_removal_available,
    render_glow_variants,
    save_cutout,
)
from src.services.stickers import (
    delete_messages,
    replace_sticker_previews,
    send_sticker_previews,
    try_create_sticker_set,
)
from src.services.pending_photo import get_pending_file_id, save_pending_photo
from src.services.telegram_files import download_file_bytes

logger = logging.getLogger(__name__)
router = Router(name="flow")


def _load_preview_message_ids(raw: str | None) -> list[int]:
    if not raw:
        return []
    try:
        return [int(x) for x in json.loads(raw)]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


async def _replace_job_preview(
    bot: Bot,
    chat_id: int,
    job_id: int,
    paths: list[Path],
    caption: str,
) -> None:
    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        previous_ids = _load_preview_message_ids(
            job.preview_message_ids if job else None
        )

    new_ids = await replace_sticker_previews(
        bot, chat_id, paths, caption, previous_message_ids=previous_ids
    )

    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job:
            job.preview_message_ids = json.dumps(new_ids)
            await session.commit()


async def _clear_job_previews(bot: Bot, chat_id: int, job_id: int) -> None:
    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None:
            return
        previous_ids = _load_preview_message_ids(job.preview_message_ids)
        job.preview_message_ids = None
        await session.commit()

    if previous_ids:
        await delete_messages(bot, chat_id, previous_ids)


@router.message(F.text == "🎨 Create stickers")
async def cmd_create(message: Message, state: FSMContext) -> None:
    await state.set_state(StickerFlow.awaiting_photo)
    await message.answer(
        "Send **one photo** with a clear main subject.\n"
        "We'll **remove the background** and add a **glowing** sticker effect.",
        parse_mode="Markdown",
    )


async def _after_photo_upload(
    message: Message, state: FSMContext, file_id: str
) -> None:
    async with SessionLocal() as session:
        pending_id = await save_pending_photo(
            session, message.from_user.id, file_id
        )
        await session.commit()

    await state.update_data(source_file_id=file_id, pending_id=pending_id)
    await state.set_state(StickerFlow.choosing_style)
    await message.answer(
        "Photo saved. Choose a **glow color**:",
        reply_markup=glow_color_keyboard(pending_id),
        parse_mode="Markdown",
    )


@router.message(F.photo)
async def on_photo(message: Message, state: FSMContext) -> None:
    """Accept photo anytime (with or without tapping Create stickers first)."""
    current = await state.get_state()
    if current == StickerFlow.preview.state:
        await message.answer(
            "Send **Create stickers** or /cancel, then send a new photo.",
            parse_mode="Markdown",
        )
        return
    photo = message.photo[-1]
    await _after_photo_upload(message, state, photo.file_id)


@router.callback_query(F.data.startswith("style:"))
async def on_style_chosen(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.split(":")
    if len(parts) < 2:
        await callback.answer("Invalid button.", show_alert=True)
        return

    glow_color = parts[1]
    pending_id = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else None

    data = await state.get_data()
    file_id = data.get("source_file_id")

    if not file_id and pending_id is not None:
        async with SessionLocal() as session:
            file_id = await get_pending_file_id(
                session, pending_id, callback.from_user.id
            )

    if not file_id:
        await callback.answer(
            "Photo expired. Send your photo again.", show_alert=True
        )
        await callback.message.answer(
            "That menu is outdated or the bot was restarted.\n"
            "Please **send your photo again** (or tap Create stickers first).",
            parse_mode="Markdown",
        )
        return

    async with SessionLocal() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        if user.credits < 1:
            await session.commit()
            if PAYMENTS_ENABLED:
                await callback.message.answer(
                    "You need **1 credit** for this generation.\n"
                    "Buy credits with Telegram Stars:",
                    parse_mode="Markdown",
                    reply_markup=buy_packages_keyboard(),
                )
            else:
                await callback.message.answer(
                    "You’re out of credits. Payments are disabled right now.\n"
                    "Message /start and try again in a minute (we’re topping up free credits).",
                    parse_mode="Markdown",
                )
            await callback.answer()
            return

        job = GenerationJob(
            user_id=user.id,
            style=glow_color,
            source_file_id=file_id,
            status="generating",
        )
        session.add(job)
        await session.flush()
        job_id = job.id

        if not await consume_credit(session, user):
            await session.commit()
            await callback.message.answer(
                "Not enough credits." if not PAYMENTS_ENABLED else "Not enough credits. Use /buy."
            )
            await callback.answer()
            return

        job.credit_charged = True
        await session.commit()

    if removebg_api_available():
        extra = " (remove.bg backup if needed)"
    else:
        extra = ""
    status = (
        f"Removing background{extra}… first run can take ~30s while the model loads.\n"
        "Then applying glow."
    )
    try:
        await callback.message.edit_text(status)
    except Exception:
        await callback.message.answer(status)

    try:
        source_bytes = await download_file_bytes(bot, file_id)
        paths = await generate_variations(
            job_id,
            glow_color,
            source_bytes,
            outline_width=2,
            glow_strength=55,
        )
    except BackgroundRemovalUnavailable as exc:
        logger.exception("Background removal unavailable for job %s", job_id)
        async with SessionLocal() as session:
            user = await get_or_create_user(session, callback.from_user.id)
            if job_id:
                job = await session.get(GenerationJob, job_id)
                if job and job.credit_charged:
                    await add_credits(session, user, 1)
                    job.credit_charged = False
                    job.status = "failed"
            await session.commit()
        await callback.message.answer(
            "Could not remove the background on the server.\n\n"
            f"{exc}\n\n"
            "Credit refunded. Stop the bot and run **run.bat** again.",
            parse_mode="Markdown",
        )
        await callback.answer()
        return
    except Exception as exc:
        logger.exception("Generation failed for job %s", job_id)
        async with SessionLocal() as session:
            user = await get_or_create_user(session, callback.from_user.id)
            if job_id:
                job = await session.get(GenerationJob, job_id)
                if job and job.credit_charged:
                    await add_credits(session, user, 1)
                    job.credit_charged = False
                    job.status = "failed"
            await session.commit()
        await callback.message.answer(
            f"Something went wrong while generating:\n`{exc}`\n\n"
            "Credit refunded. Try another photo.",
            parse_mode="Markdown",
        )
        await callback.answer()
        return

    paths_str = json.dumps([str(p) for p in paths])

    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        job.status = "preview"
        job.result_paths = paths_str
        await session.commit()

    await state.update_data(job_id=job_id)
    await state.set_state(StickerFlow.preview)

    await _replace_job_preview(
        bot,
        callback.message.chat.id,
        job_id,
        paths,
        "Preview — cutout + glow",
    )
    show_recut = quality_bg_removal_available()
    hint = (
        "Background removed and glow applied.\n"
        "Tap **Edit outline / glow** for size, glow, and outline."
    )
    if show_recut:
        hint += "\nBad cutout? Use **Better background** (needs API key in .env)."
    await callback.message.answer(
        hint,
        reply_markup=preview_keyboard(job_id, show_recut=show_recut),
    )
    await callback.answer()


async def _apply_glow_settings(
    bot: Bot,
    chat_id: int,
    job_id: int,
    size: int,
    outline: int,
    glow: int,
) -> list[Path] | None:
    size = max(50, min(150, size))
    outline = max(0, min(12, outline))
    glow = max(0, min(100, glow))

    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None:
            return None
        job.subject_scale = size
        job.outline_width = outline
        job.glow_strength = glow
        glow_color = job.style
        await session.commit()

    try:
        paths = render_glow_variants(
            job_id,
            glow_color,
            outline_width=outline,
            glow_strength=glow,
            subject_scale=size,
        )
    except Exception:
        logger.exception("Re-render failed for job %s", job_id)
        return None

    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job:
            job.result_paths = json.dumps([str(p) for p in paths])
            await session.commit()

    await _replace_job_preview(bot, chat_id, job_id, paths, "Preview — cutout + glow")
    return paths


@router.callback_query(F.data.startswith("edit:"))
async def on_edit(callback: CallbackQuery) -> None:
    job_id = int(callback.data.split(":", 1)[1])

    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None:
            await callback.answer("Job not found.", show_alert=True)
            return
        outline = job.outline_width
        glow = job.glow_strength or 55
        size = getattr(job, "subject_scale", 100) or 100

    show_recut = quality_bg_removal_available()
    await callback.message.answer(
        f"**Edit sticker**\n"
        f"Size: **{size}%** · Outline: **{outline}** · Glow: **{glow}**\n"
        "Each button updates the preview above (replaces the last image).",
        parse_mode="Markdown",
        reply_markup=edit_tune_keyboard(job_id, show_recut=show_recut),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tune:"))
async def on_tune(callback: CallbackQuery, bot: Bot) -> None:
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Invalid button.", show_alert=True)
        return

    action = parts[1]
    job_id = int(parts[2])

    if action == "done":
        await callback.message.answer(
            "Ready to deliver? Use the buttons below.",
            reply_markup=preview_keyboard(
                job_id, show_recut=quality_bg_removal_available()
            ),
        )
        await callback.answer()
        return

    if len(parts) < 4:
        await callback.answer("Invalid button.", show_alert=True)
        return

    delta = int(parts[3])

    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None:
            await callback.answer("Job not found.", show_alert=True)
            return
        outline = job.outline_width
        glow = job.glow_strength or 55
        size = getattr(job, "subject_scale", 100) or 100

    if action == "glow":
        glow = max(0, min(100, glow + delta))
    elif action == "outline":
        outline = max(0, min(12, outline + delta))
    elif action == "size":
        size = max(50, min(150, size + delta))
    else:
        await callback.answer("Invalid button.", show_alert=True)
        return

    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None:
            await callback.answer("Job not found.", show_alert=True)
            return
        job.outline_width = outline
        job.glow_strength = glow
        job.subject_scale = size
        glow_color = job.style
        await session.commit()

    try:
        paths = render_glow_variants(
            job_id,
            glow_color,
            outline_width=outline,
            glow_strength=glow,
            subject_scale=size,
        )
    except Exception:
        logger.exception("Re-render failed for job %s", job_id)
        await callback.answer("Could not update preview.", show_alert=True)
        return

    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job:
            job.result_paths = json.dumps([str(p) for p in paths])
            await session.commit()

    await _replace_job_preview(
        bot, callback.message.chat.id, job_id, paths, "Preview — cutout + glow"
    )
    await callback.answer(f"Size {size}%, outline {outline}, glow {glow}")


@router.callback_query(F.data.startswith("recut:"))
async def on_recut(callback: CallbackQuery, bot: Bot) -> None:
    job_id = int(callback.data.split(":", 1)[1])

    if not quality_bg_removal_available():
        await callback.answer(
            "Add REMOVE_BG_API_KEY or AI_API_KEY in .env for better cutouts.",
            show_alert=True,
        )
        return

    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None:
            await callback.answer("Job not found.", show_alert=True)
            return
        file_id = job.source_file_id
        glow_color = job.style
        outline = job.outline_width
        glow = job.glow_strength or 55
        size = getattr(job, "subject_scale", 100) or 100

    await callback.answer("Re-cutting background (API)…")
    try:
        source_bytes = await download_file_bytes(bot, file_id)
        await save_cutout(job_id, source_bytes, quality_first=True)
        paths = render_glow_variants(
            job_id,
            glow_color,
            outline_width=outline,
            glow_strength=glow,
            subject_scale=size,
        )
    except Exception as exc:
        logger.exception("Recut failed for job %s", job_id)
        await callback.message.answer(f"Could not improve background:\n`{exc}`")
        return

    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job:
            job.result_paths = json.dumps([str(p) for p in paths])
            await session.commit()

    await _replace_job_preview(
        bot, callback.message.chat.id, job_id, paths, "Preview — cutout + glow"
    )
    await callback.answer("Background updated")


@router.message(F.web_app_data)
async def on_web_app_data(message: Message, bot: Bot) -> None:
    try:
        payload = json.loads(message.web_app_data.data)
        job_id = int(payload["job_id"])
        size = int(payload.get("subject_scale", 100))
        outline = int(payload.get("outline_width", 2))
        glow = int(payload.get("glow_strength", 55))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        await message.answer("Invalid editor data.")
        return

    paths = await _apply_glow_settings(
        bot, message.chat.id, job_id, size, outline, glow
    )
    if paths is None:
        await message.answer("Job not found or could not update glow.")
        return

    await message.answer(
        f"Updated (size {max(50, min(150, size))}%, strength {glow}, outline {outline}). "
        "Tap **Deliver stickers** when ready.",
        parse_mode="Markdown",
        reply_markup=preview_keyboard(
            job_id, show_recut=quality_bg_removal_available()
        ),
    )


@router.callback_query(F.data.startswith("deliver:"))
async def on_deliver(callback: CallbackQuery, bot: Bot) -> None:
    job_id = int(callback.data.split(":", 1)[1])

    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None:
            await callback.answer("Job not found.", show_alert=True)
            return
        try:
            paths = render_glow_variants(
                job_id,
                job.style,
                outline_width=job.outline_width,
                glow_strength=job.glow_strength or 55,
                subject_scale=job.subject_scale or 100,
            )
            job.result_paths = json.dumps([str(p) for p in paths])
            await session.commit()
        except Exception:
            if not job.result_paths:
                await callback.answer("Job not found.", show_alert=True)
                return
            paths = [Path(p) for p in json.loads(job.result_paths)]
            await session.commit()

    uid = callback.from_user.id
    set_name = f"stickernow_{uid}_{job_id}_by_stickernow_bot"
    title = f"StickerNow #{job_id}"
    created = await try_create_sticker_set(bot, uid, set_name, title, paths)

    await _clear_job_previews(bot, callback.message.chat.id, job_id)

    if created:
        await callback.message.answer(
            f"Sticker pack created: https://t.me/addstickers/{created}\n"
            "Add it to Telegram — you're done!",
        )
    else:
        await send_sticker_previews(
            bot, callback.message.chat.id, paths, "Your stickers (PNG, Telegram-ready)"
        )
        await callback.message.answer(
            "Sent sticker files above. To publish a pack, try again or add via @Stickers."
        )

    async with SessionLocal() as session:
        job = await session.get(GenerationJob, job_id)
        if job:
            job.status = "delivered"
            job.sticker_set_name = created
            await session.commit()

    await callback.answer("Delivered!")


@router.callback_query(F.data == "flow:cancel")
async def on_cancel_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "Cancelled. Tap Create stickers." if not PAYMENTS_ENABLED else "Cancelled. Tap Create stickers or /buy."
    )
    await callback.answer()
