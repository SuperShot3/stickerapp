"""One-time: set all existing users to FREE_CREDITS_GRANT. Run: python scripts/grant_all_credits.py"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from src.config import FREE_CREDITS_GRANT
from src.db.database import SessionLocal, init_db
from src.db.models import User
from src.services.credits import apply_free_credit_grant


async def main() -> None:
    await init_db()
    async with SessionLocal() as session:
        users = (await session.execute(select(User))).scalars().all()
        for user in users:
            apply_free_credit_grant(user)
        await session.commit()
        print(f"Updated {len(users)} user(s) to at least {FREE_CREDITS_GRANT} credits.")


if __name__ == "__main__":
    asyncio.run(main())
