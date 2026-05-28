from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import PendingPhoto


async def save_pending_photo(
    session: AsyncSession, telegram_id: int, file_id: str
) -> int:
    await session.execute(
        delete(PendingPhoto).where(PendingPhoto.telegram_id == telegram_id)
    )
    row = PendingPhoto(telegram_id=telegram_id, file_id=file_id)
    session.add(row)
    await session.flush()
    return row.id


async def get_pending_file_id(
    session: AsyncSession, pending_id: int, telegram_id: int
) -> str | None:
    result = await session.execute(
        select(PendingPhoto).where(
            PendingPhoto.id == pending_id,
            PendingPhoto.telegram_id == telegram_id,
        )
    )
    row = result.scalar_one_or_none()
    return row.file_id if row else None
