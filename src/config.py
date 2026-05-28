"""App configuration. Package prices are in Telegram Stars (XTR), not fiat."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class CreditPackage:
    id: str
    title: str
    description: str
    credits: int
    stars: int  # XTR amount (whole Stars)


# 1 credit = 1 photo → 1 sticker
CREDIT_PACKAGES: tuple[CreditPackage, ...] = (
    CreditPackage(
        id="pack_1",
        title="1 generation",
        description="1 credit — one glowing sticker from one photo.",
        credits=1,
        stars=50,
    ),
    CreditPackage(
        id="pack_10",
        title="10 generations",
        description="10 credits — 10 glowing stickers from your photos.",
        credits=10,
        stars=400,
    ),
)

PACKAGES_BY_ID = {p.id: p for p in CREDIT_PACKAGES}

# Glow color presets (after background removal)
GLOW_PRESETS: tuple[tuple[str, str], ...] = (
    ("cyan", "Cyan glow"),
    ("pink", "Pink glow"),
    ("gold", "Gold glow"),
    ("white", "White glow"),
    ("purple", "Purple glow"),
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
BOT_SECRET = os.environ.get("BOT_SECRET", "change-me-in-production")
DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite+aiosqlite:///{ROOT / 'data' / 'stickerbot.db'}"
)
MINI_APP_URL = os.environ.get("MINI_APP_URL", "").rstrip("/") + "/"
MINIAPP_PORT = int(os.environ.get("MINIAPP_PORT", "8080"))
MINIAPP_ENABLED = os.environ.get("MINIAPP_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)

# Temporarily disable monetization while growing visitors.
# When false: hide /buy + Stars UI and do not register payment handlers.
PAYMENTS_ENABLED = os.environ.get("PAYMENTS_ENABLED", "false").lower() in (
    "1",
    "true",
    "yes",
)
ADMIN_TELEGRAM_IDS: frozenset[int] = frozenset(
    int(x.strip())
    for x in os.environ.get("ADMIN_TELEGRAM_IDS", "").split(",")
    if x.strip()
)

AI_API_KEY = os.environ.get("AI_API_KEY", "").strip()
AI_API_URL = os.environ.get("AI_API_URL", "").strip()
AI_API_BASE = (AI_API_URL or "https://api.openai.com/v1").rstrip("/")
AI_IMAGE_MODEL = os.environ.get("AI_IMAGE_MODEL", "gpt-image-1.5").strip()
AI_EDIT_PROMPT = os.environ.get("AI_EDIT_PROMPT", "").strip()

# Optional USD estimates for /apicost (per 1M tokens — check https://openai.com/api/pricing)
def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


AI_USD_PER_1M_INPUT_TOKENS = _env_float("AI_USD_PER_1M_INPUT_TOKENS", 8.0)
AI_USD_PER_1M_OUTPUT_TOKENS = _env_float("AI_USD_PER_1M_OUTPUT_TOKENS", 32.0)
# remove.bg bills in API credits (~1 credit per image on many plans)
REMOVEBG_USD_PER_CREDIT = _env_float("REMOVEBG_USD_PER_CREDIT", 0.0)

# Dedicated BG removal API (https://www.remove.bg/api) — tried after rembg fails
REMOVE_BG_API_KEY = os.environ.get("REMOVE_BG_API_KEY", "").strip()

# OpenAI edit as last-resort BG removal (not enhancement). Also reads legacy AI_ENHANCE_ENABLED.
_ai_bg_raw = (
    os.environ.get("AI_BG_FALLBACK_ENABLED", "")
    or os.environ.get("AI_ENHANCE_ENABLED", "")
).strip().lower()
if _ai_bg_raw:
    AI_BG_FALLBACK_ENABLED = _ai_bg_raw in ("1", "true", "yes")
else:
    AI_BG_FALLBACK_ENABLED = bool(AI_API_KEY)

# Dev / testing: grant at least this many credits on each bot interaction (0 = disabled)
FREE_CREDITS_GRANT = int(os.environ.get("FREE_CREDITS_GRANT", "500"))

# Local background removal via rembg (pip install rembg). No API key needed.
REMOVE_BG_ENABLED = os.environ.get("REMOVE_BG_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)

CURRENCY = "XTR"
PROVIDER_TOKEN = ""  # Required empty string for Telegram Stars
