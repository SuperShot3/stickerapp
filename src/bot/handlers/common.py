from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.bot.keyboards import buy_packages_keyboard, main_menu
from src.config import FREE_CREDITS_GRANT, PAYMENTS_ENABLED
from src.db.database import SessionLocal
from src.services.credits import get_or_create_user
from src.services.payments import all_packages_summary

router = Router(name="common")

PAYSUPPORT_TEXT = (
    "Payment support — StickerNow\n\n"
    "We sell digital sticker generation credits paid with Telegram Stars only.\n"
    "1 credit = one photo processed into one glowing sticker.\n\n"
    "Packages:\n"
    "{packages}\n\n"
    "Issues with a charge? Reply here with your @username and approximate payment time. "
    "Refunds are handled via Telegram within 21 days where applicable.\n\n"
    "Commands: /buy — purchase credits · /balance — your balance"
)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    async with SessionLocal() as session:
        user = await get_or_create_user(session, message.from_user.id)
        await session.commit()
        balance = user.credits

    testing_note = (
        "\n\n_Testing: free credits enabled._"
        if FREE_CREDITS_GRANT > 0
        else ""
    )
    payments_note = (
        "\n\n_Payments are temporarily disabled while we grow._"
        if not PAYMENTS_ENABLED
        else "\n\nBuy more with /buy (Telegram Stars ⭐ only)."
    )
    await message.answer(
        "Welcome to **StickerNow** — glowing stickers in Telegram.\n\n"
        "1. Send a photo (one clear subject)\n"
        "2. We **remove the background**\n"
        "3. You pick a **glow color** and strength\n"
        "4. Get Telegram-ready sticker files\n\n"
        f"Your balance: **{balance}** credit(s).\n"
        f"{payments_note}{testing_note}",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    payments_lines = (
        "/buy — buy credit packages (Stars)\n"
        "/paysupport — payment help\n"
        if PAYMENTS_ENABLED
        else ""
    )
    await message.answer(
        "**Commands**\n"
        "/start — main menu\n"
        "/balance — credit balance\n"
        f"{payments_lines}"
        "/cancel — cancel current flow\n"
        "(Admins: /apicost — OpenAI & remove.bg spend)\n\n"
        "**How it works:** send a photo → we cut out the subject → you choose glow color.\n"
        "On preview: **Edit** for bigger/smaller, glow, outline; **Better background** if you set a remove.bg or OpenAI key.\n\n"
        "Tap **Create stickers** to begin.",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message) -> None:
    if not PAYMENTS_ENABLED:
        await message.answer("Payments are disabled for now.")
        return
    await message.answer(
        PAYSUPPORT_TEXT.format(packages=all_packages_summary()),
        parse_mode="Markdown",
    )


@router.message(Command("balance"))
@router.message(lambda m: m.text and "balance" in m.text.lower())
async def cmd_balance(message: Message) -> None:
    async with SessionLocal() as session:
        user = await get_or_create_user(session, message.from_user.id)
        await session.commit()
        credits = user.credits
    await message.answer(f"You have **{credits}** generation credit(s).", parse_mode="Markdown")


@router.message(Command("buy"))
@router.message(lambda m: m.text and "buy credit" in m.text.lower())
async def cmd_buy(message: Message) -> None:
    if not PAYMENTS_ENABLED:
        await message.answer("Payments are disabled for now.")
        return
    await message.answer(
        "Choose a credit package (paid with Telegram Stars ⭐):\n\n"
        + all_packages_summary(),
        reply_markup=buy_packages_keyboard(),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Cancelled. Send a photo when ready.")
