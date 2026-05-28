"""Track paid API usage (OpenAI tokens, remove.bg credits) per generation job."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from src.config import (
    AI_IMAGE_MODEL,
    AI_USD_PER_1M_INPUT_TOKENS,
    AI_USD_PER_1M_OUTPUT_TOKENS,
    REMOVEBG_USD_PER_CREDIT,
)
from src.db.database import SessionLocal
from src.db.models import ApiUsageLog

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApiUsageSnapshot:
    provider: str  # openai | removebg
    operation: str = "bg_removal"
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    api_credits: float | None = None
    estimated_usd: float | None = None
    raw_usage: dict | None = None


def snapshot_from_openai_usage(
    usage: dict | None,
    *,
    model: str | None = None,
) -> ApiUsageSnapshot | None:
    if not usage:
        return None
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = int(input_tokens) + int(output_tokens)

    est = estimate_openai_image_usd(
        input_tokens=int(input_tokens) if input_tokens is not None else None,
        output_tokens=int(output_tokens) if output_tokens is not None else None,
    )
    return ApiUsageSnapshot(
        provider="openai",
        operation="bg_removal",
        model=model or AI_IMAGE_MODEL,
        input_tokens=int(input_tokens) if input_tokens is not None else None,
        output_tokens=int(output_tokens) if output_tokens is not None else None,
        total_tokens=int(total_tokens) if total_tokens is not None else None,
        estimated_usd=est,
        raw_usage=usage,
    )


def snapshot_from_removebg(
    credits_charged: float | None,
) -> ApiUsageSnapshot | None:
    if credits_charged is None:
        return None
    est = None
    if REMOVEBG_USD_PER_CREDIT > 0:
        est = round(credits_charged * REMOVEBG_USD_PER_CREDIT, 6)
    return ApiUsageSnapshot(
        provider="removebg",
        operation="bg_removal",
        api_credits=credits_charged,
        estimated_usd=est,
    )


def estimate_openai_image_usd(
    *,
    input_tokens: int | None,
    output_tokens: int | None,
) -> float | None:
    if input_tokens is None and output_tokens is None:
        return None
    if AI_USD_PER_1M_INPUT_TOKENS <= 0 and AI_USD_PER_1M_OUTPUT_TOKENS <= 0:
        return None
    cost = 0.0
    if input_tokens and AI_USD_PER_1M_INPUT_TOKENS > 0:
        cost += input_tokens * AI_USD_PER_1M_INPUT_TOKENS / 1_000_000
    if output_tokens and AI_USD_PER_1M_OUTPUT_TOKENS > 0:
        cost += output_tokens * AI_USD_PER_1M_OUTPUT_TOKENS / 1_000_000
    return round(cost, 6) if cost > 0 else None


async def record_api_usage(
    job_id: int | None,
    snapshot: ApiUsageSnapshot | None,
) -> None:
    if snapshot is None:
        return

    row = ApiUsageLog(
        job_id=job_id,
        provider=snapshot.provider,
        operation=snapshot.operation,
        model=snapshot.model,
        input_tokens=snapshot.input_tokens,
        output_tokens=snapshot.output_tokens,
        total_tokens=snapshot.total_tokens,
        api_credits=snapshot.api_credits,
        estimated_usd=snapshot.estimated_usd,
        raw_usage=json.dumps(snapshot.raw_usage) if snapshot.raw_usage else None,
    )
    async with SessionLocal() as session:
        session.add(row)
        await session.commit()

    parts = [f"provider={snapshot.provider}", f"job={job_id}"]
    if snapshot.total_tokens is not None:
        parts.append(f"tokens={snapshot.total_tokens}")
    if snapshot.api_credits is not None:
        parts.append(f"removebg_credits={snapshot.api_credits}")
    if snapshot.estimated_usd is not None:
        parts.append(f"est_usd=${snapshot.estimated_usd:.4f}")
    logger.info("API usage recorded: %s", ", ".join(parts))


def _fmt_usd(value: float | None) -> str:
    if value is None:
        return "—"
    if value < 0.01:
        return f"${value:.4f}"
    return f"${value:.2f}"


async def format_usage_report(*, days: int = 30, job_id: int | None = None) -> str:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    async with SessionLocal() as session:
        base = select(ApiUsageLog).where(ApiUsageLog.created_at >= since)
        if job_id is not None:
            base = base.where(ApiUsageLog.job_id == job_id)

        rows = (await session.execute(base.order_by(ApiUsageLog.created_at.desc()))).scalars().all()

        by_provider = await session.execute(
            select(
                ApiUsageLog.provider,
                func.count(ApiUsageLog.id),
                func.sum(ApiUsageLog.total_tokens),
                func.sum(ApiUsageLog.api_credits),
                func.sum(ApiUsageLog.estimated_usd),
            )
            .where(ApiUsageLog.created_at >= since)
            .group_by(ApiUsageLog.provider)
        )

    if job_id is not None:
        title = f"API spend — job #{job_id}"
    else:
        title = f"API spend — last {days} day(s)"

    if not rows:
        return f"{title}\n\nNo paid API calls recorded in this period."

    lines = [f"**{title}**", ""]
    lines.append("**By provider**")
    for provider, count, tokens, credits, usd in by_provider:
        token_part = f", {int(tokens or 0):,} tokens" if tokens else ""
        credit_part = f", {float(credits or 0):.1f} remove.bg credits" if credits else ""
        lines.append(
            f"· **{provider}**: {count} call(s){token_part}{credit_part} — est. {_fmt_usd(float(usd) if usd else None)}"
        )

    total_usd = sum(r.estimated_usd or 0 for r in rows)
    if any(r.estimated_usd for r in rows):
        lines.append("")
        lines.append(f"**Total estimated:** {_fmt_usd(total_usd)}")

    lines.append("")
    lines.append("**Recent calls** (newest first)")
    for r in rows[:15]:
        when = r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "?"
        job = f"job #{r.job_id}" if r.job_id else "no job"
        detail = []
        if r.total_tokens is not None:
            detail.append(f"{r.total_tokens:,} tok")
        if r.api_credits is not None:
            detail.append(f"{r.api_credits:.2f} cr")
        if r.estimated_usd is not None:
            detail.append(_fmt_usd(r.estimated_usd))
        extra = f" ({', '.join(detail)})" if detail else ""
        model = f" · {r.model}" if r.model else ""
        lines.append(f"· {when} · {r.provider}{model} · {job}{extra}")

    lines.append("")
    lines.append(
        "_Estimates use AI_USD_PER_1M_* and REMOVEBG_USD_PER_CREDIT from .env. "
        "OpenAI image calls return token usage in the API response._"
    )
    return "\n".join(lines)
