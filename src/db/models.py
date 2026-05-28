from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    jobs: Mapped[list[GenerationJob]] = relationship(back_populates="user")
    payments: Mapped[list[StarPayment]] = relationship(back_populates="user")


class PendingPhoto(Base):
    """Links glow-color buttons to an uploaded photo (survives bot restarts)."""

    __tablename__ = "pending_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    file_id: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class StarPayment(Base):
    __tablename__ = "star_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    package_id: Mapped[str] = mapped_column(String(32))
    credits_granted: Mapped[int] = mapped_column(Integer)
    stars_amount: Mapped[int] = mapped_column(Integer)
    telegram_payment_charge_id: Mapped[str] = mapped_column(String(128), unique=True)
    invoice_payload: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="payments")


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    style: Mapped[str] = mapped_column(String(32))
    source_file_id: Mapped[str] = mapped_column(String(256))
    outline_width: Mapped[int] = mapped_column(Integer, default=2)
    glow_strength: Mapped[int] = mapped_column(Integer, default=55)
    subject_scale: Mapped[int] = mapped_column(Integer, default=100)
    result_paths: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_message_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    sticker_set_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    credit_charged: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="jobs")


class ApiUsageLog(Base):
    """Paid third-party API calls (OpenAI, remove.bg) linked to a generation job."""

    __tablename__ = "api_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("generation_jobs.id"), index=True, nullable=True
    )
    provider: Mapped[str] = mapped_column(String(32), index=True)
    operation: Mapped[str] = mapped_column(String(32), default="bg_removal")
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_credits: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_usage: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
