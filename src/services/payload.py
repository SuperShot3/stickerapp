"""Signed invoice payloads (max 128 bytes for Telegram)."""

from __future__ import annotations

import hashlib
import hmac

from src.config import BOT_SECRET, PACKAGES_BY_ID


def build_invoice_payload(package_id: str, telegram_user_id: int) -> str:
    if package_id not in PACKAGES_BY_ID:
        raise ValueError(f"Unknown package: {package_id}")
    body = f"{package_id}:{telegram_user_id}"
    sig = hmac.new(
        BOT_SECRET.encode(), body.encode(), hashlib.sha256
    ).hexdigest()[:12]
    payload = f"{body}:{sig}"
    if len(payload.encode()) > 128:
        raise ValueError("Invoice payload too long")
    return payload


def parse_and_verify_payload(payload: str) -> tuple[str, int]:
    parts = payload.split(":")
    if len(parts) != 3:
        raise ValueError("Invalid payload format")
    package_id, user_id_str, sig = parts
    body = f"{package_id}:{user_id_str}"
    expected = hmac.new(
        BOT_SECRET.encode(), body.encode(), hashlib.sha256
    ).hexdigest()[:12]
    if not hmac.compare_digest(sig, expected):
        raise ValueError("Invalid payload signature")
    return package_id, int(user_id_str)
