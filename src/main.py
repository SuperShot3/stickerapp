"""StickerNow — Telegram bot + Mini App. Payments: Telegram Stars (XTR) only."""

from __future__ import annotations

import asyncio
import atexit
import logging
import os
import sys
from pathlib import Path

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from src.bot.handlers import common, flow, payments
from src.config import (
    BOT_TOKEN,
    MINI_APP_URL,
    MINIAPP_ENABLED,
    MINIAPP_PORT,
    PAYMENTS_ENABLED,
    REMOVE_BG_ENABLED,
)
from src.db.database import init_db
from src.services.background import background_removal_available

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MINIAPP_DIR = Path(__file__).parent / "miniapp"
PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"
_LOCK_PATH = Path(__file__).resolve().parent.parent / ".bot.lock"
_lock_file = None


def _acquire_single_instance_lock() -> None:
    """Telegram allows only one long-polling getUpdates client per bot token."""
    global _lock_file
    _lock_file = open(_LOCK_PATH, "a+", encoding="utf-8")
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        _lock_file.close()
        _lock_file = None
        logger.error(
            "Another bot instance is already running. "
            "Close other terminals using run.bat / run.ps1, then start once."
        )
        raise SystemExit(1) from None
    _lock_file.seek(0)
    _lock_file.truncate()
    _lock_file.write(str(os.getpid()))
    _lock_file.flush()


def _release_single_instance_lock() -> None:
    global _lock_file
    if _lock_file is None:
        return
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(_lock_file.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    _lock_file.close()
    _lock_file = None


async def miniapp_handler(request: web.Request) -> web.StreamResponse:
    path = request.match_info.get("path", "index.html") or "index.html"
    file_path = (MINIAPP_DIR / path).resolve()
    if not str(file_path).startswith(str(MINIAPP_DIR.resolve())):
        raise web.HTTPNotFound()
    if not file_path.is_file():
        file_path = MINIAPP_DIR / "index.html"
    return web.FileResponse(file_path)


async def run_miniapp_server(port: int) -> web.AppRunner | None:
    if not MINIAPP_ENABLED:
        logger.info("Mini App server disabled (MINIAPP_ENABLED=false)")
        return None

    app = web.Application()
    if (PUBLIC_DIR / "content").is_dir():
        app.router.add_static("/content/", path=(PUBLIC_DIR / "content"), show_index=False)
    app.router.add_get("/miniapp/", miniapp_handler)
    app.router.add_get("/miniapp/{path:.*}", miniapp_handler)
    runner = web.AppRunner(app)
    await runner.setup()

    for attempt in range(5):
        bind_port = port + attempt
        try:
            site = web.TCPSite(runner, "0.0.0.0", bind_port)
            await site.start()
            logger.info(
                "Mini App static server on http://127.0.0.1:%s/miniapp/", bind_port
            )
            if bind_port != port:
                logger.warning(
                    "Port %s was busy; using %s instead. Stop other bot instances or set MINIAPP_PORT.",
                    port,
                    bind_port,
                )
            if not MINI_APP_URL or MINI_APP_URL == "/":
                logger.warning(
                    "Set MINI_APP_URL in .env to your public HTTPS URL (e.g. ngrok) "
                    "and register in @BotFather"
                )
            return runner
        except OSError as exc:
            if exc.errno != 10048 and getattr(exc, "winerror", None) != 10048:
                await runner.cleanup()
                raise
            logger.warning("Port %s in use, trying next port…", bind_port)

    await runner.cleanup()
    logger.warning(
        "Could not start Mini App server (ports %s–%s busy). "
        "Bot will still run; stop the other process or set MINIAPP_ENABLED=false.",
        port,
        port + 4,
    )
    return None


async def main() -> None:
    _acquire_single_instance_lock()
    atexit.register(_release_single_instance_lock)

    await init_db()

    if REMOVE_BG_ENABLED and not background_removal_available():
        logger.error(
            'REMOVE_BG_ENABLED=true but rembg is not usable. '
            'Install with: pip install "rembg[cpu]" then restart the bot.'
        )
        raise SystemExit(1)
    if REMOVE_BG_ENABLED:
        logger.info("Background removal: rembg ready")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(common.router)
    if PAYMENTS_ENABLED:
        dp.include_router(payments.router)
    dp.include_router(flow.router)

    miniapp_runner = await run_miniapp_server(MINIAPP_PORT)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Main menu"),
            BotCommand(command="balance", description="Credit balance"),
            BotCommand(command="help", description="How it works"),
            BotCommand(command="cancel", description="Cancel current step"),
        ]
    )
    if PAYMENTS_ENABLED:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Main menu"),
                BotCommand(command="buy", description="Buy credits (Stars)"),
                BotCommand(command="balance", description="Credit balance"),
                BotCommand(command="paysupport", description="Payment help"),
                BotCommand(command="help", description="How it works"),
                BotCommand(command="cancel", description="Cancel current step"),
            ]
        )

    try:
        logger.info("Starting @stickernow_bot (polling)")
        await dp.start_polling(bot)
    finally:
        if miniapp_runner is not None:
            await miniapp_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
