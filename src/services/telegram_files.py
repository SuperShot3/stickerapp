from __future__ import annotations

from aiogram import Bot


async def download_file_bytes(bot: Bot, file_id: str) -> bytes:
    tg_file = await bot.get_file(file_id)
    if not tg_file.file_path:
        raise ValueError("Photo unavailable (too large or expired). Send again.")
    stream = await bot.download_file(tg_file.file_path)
    if stream is None:
        raise ValueError("Could not download photo from Telegram.")
    try:
        data = stream.read()
    finally:
        if hasattr(stream, "close"):
            stream.close()
    if not data:
        raise ValueError("Downloaded photo is empty.")
    return data
