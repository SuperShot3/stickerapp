from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import DATABASE_URL, ROOT
from src.db.models import Base


def _migrate_generation_jobs(sync_conn) -> None:
    inspector = inspect(sync_conn)
    if "generation_jobs" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("generation_jobs")}
    if "subject_scale" not in columns:
        sync_conn.execute(
            text(
                "ALTER TABLE generation_jobs "
                "ADD COLUMN subject_scale INTEGER NOT NULL DEFAULT 100"
            )
        )
    if "preview_message_ids" not in columns:
        sync_conn.execute(
            text("ALTER TABLE generation_jobs ADD COLUMN preview_message_ids TEXT")
        )


def _ensure_data_dir() -> None:
    data = ROOT / "data"
    data.mkdir(parents=True, exist_ok=True)


_ensure_data_dir()
engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_generation_jobs)
