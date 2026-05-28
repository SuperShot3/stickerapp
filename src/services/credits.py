from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import FREE_CREDITS_GRANT
from src.db.models import User


def apply_free_credit_grant(user: User) -> None:
    """Testing: ensure user has at least FREE_CREDITS_GRANT credits."""
    if FREE_CREDITS_GRANT > 0 and user.credits < FREE_CREDITS_GRANT:
        user.credits = FREE_CREDITS_GRANT


async def get_or_create_user(session: AsyncSession, telegram_id: int) -> User:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=telegram_id,
            credits=FREE_CREDITS_GRANT if FREE_CREDITS_GRANT > 0 else 0,
        )
        session.add(user)
        await session.flush()
    else:
        apply_free_credit_grant(user)
        await session.flush()
    return user


async def add_credits(session: AsyncSession, user: User, amount: int) -> int:
    user.credits += amount
    await session.flush()
    return user.credits


async def consume_credit(session: AsyncSession, user: User) -> bool:
    if user.credits < 1:
        return False
    user.credits -= 1
    await session.flush()
    return True
