"""Deliver stickers inside Telegram (send files + optional sticker set)."""

from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, InputSticker

logger = logging.getLogger(__name__)


async def delete_messages(bot: Bot, chat_id: int, message_ids: list[int]) -> None:
    for message_id in message_ids:
        try:
            await bot.delete_message(chat_id, message_id)
        except TelegramBadRequest:
            pass
        except Exception as exc:
            logger.debug("delete_message %s failed: %s", message_id, exc)


async def replace_sticker_previews(
    bot: Bot,
    chat_id: int,
    paths: list[Path],
    caption: str,
    *,
    previous_message_ids: list[int] | None = None,
) -> list[int]:
    """Delete old preview file messages, then send the new preview(s). Returns new message IDs."""
    if previous_message_ids:
        await delete_messages(bot, chat_id, previous_message_ids)

    message_ids: list[int] = []
    for i, path in enumerate(paths, start=1):
        doc_caption = f"{caption} — variation {i}" if len(paths) > 1 else caption
        msg = await bot.send_document(
            chat_id,
            document=FSInputFile(path),
            caption=doc_caption,
        )
        message_ids.append(msg.message_id)
    return message_ids


async def send_sticker_previews(
    bot: Bot, chat_id: int, paths: list[Path], caption: str
) -> list[int]:
    """Send preview file(s) without deleting prior messages."""
    return await replace_sticker_previews(
        bot, chat_id, paths, caption, previous_message_ids=None
    )


async def try_create_sticker_set(
    bot: Bot,
    user_id: int,
    set_name: str,
    title: str,
    paths: list[Path],
) -> str | None:
    if not paths:
        return None

    stickers = [
        InputSticker(
            sticker=FSInputFile(p),
            format="static",
            emoji_list=["✨"],
        )
        for p in paths[:1]
    ]
    try:
        await bot.create_new_sticker_set(
            user_id=user_id,
            name=set_name,
            title=title,
            stickers=stickers,
            sticker_type="regular",
        )
        return set_name
    except Exception as exc:
        logger.warning("create_new_sticker_set failed: %s", exc)
        return None
