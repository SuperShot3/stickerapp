from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from src.config import ADMIN_TELEGRAM_IDS, CREDIT_PACKAGES, CURRENCY, PACKAGES_BY_ID, PROVIDER_TOKEN
from src.services.api_usage import format_usage_report
from src.db.database import SessionLocal
from src.services.payload import build_invoice_payload
from src.services.payments import (
    apply_successful_payment,
    validate_pre_checkout,
)

logger = logging.getLogger(__name__)
router = Router(name="payments")


async def _send_package_invoice(bot: Bot, chat_id: int, package_id: str, user_id: int) -> None:
    package = PACKAGES_BY_ID[package_id]
    payload = build_invoice_payload(package_id, user_id)
    await bot.send_invoice(
        chat_id=chat_id,
        title=package.title,
        description=package.description,
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency=CURRENCY,
        prices=[LabeledPrice(label=package.title, amount=package.stars)],
    )


@router.callback_query(F.data.startswith("buy:"))
async def on_buy_package(callback: CallbackQuery, bot: Bot) -> None:
    package_id = callback.data.split(":", 1)[1]
    if package_id not in PACKAGES_BY_ID:
        await callback.answer("Unknown package.", show_alert=True)
        return
    await _send_package_invoice(bot, callback.message.chat.id, package_id, callback.from_user.id)
    await callback.answer()


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    try:
        package_id, credits = validate_pre_checkout(
            query.invoice_payload,
            query.from_user.id,
            query.total_amount,
            query.currency,
        )
        await query.answer(ok=True)
        logger.info(
            "pre_checkout ok user=%s package=%s credits=%s",
            query.from_user.id,
            package_id,
            credits,
        )
    except ValueError as exc:
        logger.warning("pre_checkout rejected: %s", exc)
        await query.answer(ok=False, error_message=str(exc))


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    payment = message.successful_payment
    try:
        package_id, _ = validate_pre_checkout(
            payment.invoice_payload,
            message.from_user.id,
            payment.total_amount,
            payment.currency,
        )
        package = PACKAGES_BY_ID[package_id]
    except ValueError as exc:
        logger.error("successful_payment validation failed: %s", exc)
        await message.answer(
            "Payment received but could not be verified. Contact /paysupport with your receipt."
        )
        return

    async with SessionLocal() as session:
        user, record, created = await apply_successful_payment(
            session,
            telegram_user_id=message.from_user.id,
            package_id=package_id,
            stars_amount=payment.total_amount,
            credits=package.credits,
            charge_id=payment.telegram_payment_charge_id,
            invoice_payload=payment.invoice_payload,
        )
        await session.commit()
        balance = user.credits

    if created:
        await message.answer(
            f"Thank you! **{package.credits}** credit(s) added.\n"
            f"Balance: **{balance}**. Send a photo to create stickers.",
            parse_mode="Markdown",
        )
    else:
        await message.answer(
            f"Payment already recorded. Balance: **{balance}** credit(s).",
            parse_mode="Markdown",
        )


@router.message(Command("apicost"))
async def cmd_apicost(message: Message) -> None:
    """Admin: API token/credit spend for OpenAI and remove.bg."""
    if message.from_user.id not in ADMIN_TELEGRAM_IDS:
        await message.answer("Not authorized.")
        return

    parts = (message.text or "").split()
    job_id: int | None = None
    days = 30
    if len(parts) >= 2:
        if parts[1].isdigit():
            job_id = int(parts[1])
        elif parts[1].startswith("job:") and parts[1][4:].isdigit():
            job_id = int(parts[1][4:])
    if len(parts) >= 3 and parts[-1].isdigit():
        days = max(1, min(365, int(parts[-1])))

    report = await format_usage_report(days=days, job_id=job_id)
    await message.answer(report, parse_mode="Markdown")


@router.message(Command("refund"))
async def cmd_refund(message: Message, bot: Bot) -> None:
    """Admin: /refund <telegram_user_id> <telegram_payment_charge_id>"""
    from src.config import ADMIN_TELEGRAM_IDS

    if message.from_user.id not in ADMIN_TELEGRAM_IDS:
        await message.answer("Not authorized.")
        return

    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer(
            "Usage: /refund <user_id> <telegram_payment_charge_id>\n"
            "Uses Telegram refundStarPayment API."
        )
        return

    try:
        target_user_id = int(parts[1])
        charge_id = parts[2]
    except ValueError:
        await message.answer("Invalid user id.")
        return

    try:
        await bot.refund_star_payment(
            user_id=target_user_id,
            telegram_payment_charge_id=charge_id,
        )
    except Exception as exc:
        logger.exception("refund failed")
        await message.answer(f"Refund failed: {exc}")
        return

    async with SessionLocal() as session:
        from sqlalchemy import select

        from src.db.models import StarPayment, User
        from src.services.credits import get_or_create_user

        result = await session.execute(
            select(StarPayment).where(
                StarPayment.telegram_payment_charge_id == charge_id
            )
        )
        record = result.scalar_one_or_none()
        if record:
            user = await session.get(User, record.user_id)
            if user and user.credits >= record.credits_granted:
                user.credits -= record.credits_granted
            await session.commit()

    await message.answer("Refund submitted via Telegram. Credits adjusted if applicable.")
