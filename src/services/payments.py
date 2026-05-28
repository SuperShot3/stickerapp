from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import PACKAGES_BY_ID
from src.db.models import StarPayment, User
from src.services.credits import add_credits, get_or_create_user
from src.services.payload import parse_and_verify_payload


def validate_pre_checkout(
    payload: str, telegram_user_id: int, total_amount: int, currency: str
) -> tuple[str, int]:
    if currency != "XTR":
        raise ValueError("Only Telegram Stars (XTR) are accepted.")
    package_id, payload_user_id = parse_and_verify_payload(payload)
    if payload_user_id != telegram_user_id:
        raise ValueError("Payment does not match this user.")
    package = PACKAGES_BY_ID[package_id]
    if total_amount != package.stars:
        raise ValueError("Incorrect Stars amount for this package.")
    return package_id, package.credits


async def apply_successful_payment(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    package_id: str,
    stars_amount: int,
    credits: int,
    charge_id: str,
    invoice_payload: str,
) -> tuple[User, StarPayment, bool]:
    """Returns (user, payment, created). Idempotent on charge_id."""
    existing = await session.execute(
        select(StarPayment).where(
            StarPayment.telegram_payment_charge_id == charge_id
        )
    )
    payment = existing.scalar_one_or_none()
    if payment is not None:
        user = await session.get(User, payment.user_id)
        assert user is not None
        return user, payment, False

    user = await get_or_create_user(session, telegram_user_id)
    payment = StarPayment(
        user_id=user.id,
        package_id=package_id,
        credits_granted=credits,
        stars_amount=stars_amount,
        telegram_payment_charge_id=charge_id,
        invoice_payload=invoice_payload,
    )
    session.add(payment)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing = await session.execute(
            select(StarPayment).where(
                StarPayment.telegram_payment_charge_id == charge_id
            )
        )
        payment = existing.scalar_one()
        user = await session.get(User, payment.user_id)
        assert user is not None
        return user, payment, False

    await add_credits(session, user, credits)
    return user, payment, True


def package_label(package_id: str) -> str:
    p = PACKAGES_BY_ID[package_id]
    return f"{p.title} — {p.credits} credits ({p.stars} ⭐)"


def all_packages_summary() -> str:
    lines = [
        f"• {p.title}: {p.credits} credits — {p.stars} Stars"
        for p in CREDIT_PACKAGES
    ]
    return "\n".join(lines)
