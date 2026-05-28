from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from src.config import CREDIT_PACKAGES, GLOW_PRESETS, MINI_APP_URL, PAYMENTS_ENABLED


def main_menu() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🎨 Create stickers")],
        [KeyboardButton(text="📊 Balance")],
        [KeyboardButton(text="❓ Help")],
    ]
    if PAYMENTS_ENABLED:
        rows.insert(1, [KeyboardButton(text="💫 Buy credits"), KeyboardButton(text="📊 Balance")])
        rows.pop(2)
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
    )


def glow_color_keyboard(pending_id: int) -> InlineKeyboardMarkup:
    """pending_id ties buttons to the uploaded photo (works after bot restart)."""
    rows = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=f"style:{key}:{pending_id}",
            )
        ]
        for key, label in GLOW_PRESETS
    ]
    rows.append([InlineKeyboardButton(text="Cancel", callback_data="flow:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def edit_tune_keyboard(job_id: int, *, show_recut: bool = False) -> InlineKeyboardMarkup:
    """In-chat glow/outline/size controls (works without Mini App / HTTPS)."""
    jid = str(job_id)
    rows = [
        [
            InlineKeyboardButton(
                text="Smaller", callback_data=f"tune:size:{jid}:-10"
            ),
            InlineKeyboardButton(
                text="Bigger", callback_data=f"tune:size:{jid}:10"
            ),
        ],
        [
            InlineKeyboardButton(
                text="Glow −", callback_data=f"tune:glow:{jid}:-10"
            ),
            InlineKeyboardButton(
                text="Glow +", callback_data=f"tune:glow:{jid}:10"
            ),
        ],
        [
            InlineKeyboardButton(
                text="Outline −", callback_data=f"tune:outline:{jid}:-1"
            ),
            InlineKeyboardButton(
                text="Outline +", callback_data=f"tune:outline:{jid}:1"
            ),
        ],
    ]
    if show_recut:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Better background (API)",
                    callback_data=f"recut:{jid}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="Done — deliver when ready",
                callback_data=f"tune:done:{jid}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def preview_keyboard(job_id: int, *, show_recut: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text="✏️ Edit outline / glow", callback_data=f"edit:{job_id}"
        ),
        InlineKeyboardButton(
            text="✅ Deliver stickers", callback_data=f"deliver:{job_id}"
        ),
    ]
    web_row = []
    if MINI_APP_URL and MINI_APP_URL != "/":
        web_row.append(
            InlineKeyboardButton(
                text="Open editor (Mini App)",
                web_app=WebAppInfo(url=f"{MINI_APP_URL}?job={job_id}"),
            )
        )
    rows = [buttons]
    if web_row:
        rows.insert(0, web_row)
    if show_recut:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Better background (API)",
                    callback_data=f"recut:{job_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Start over", callback_data="flow:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def buy_packages_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{p.title} — {p.stars} ⭐",
                    callback_data=f"buy:{p.id}",
                )
            ]
            for p in CREDIT_PACKAGES
        ]
    )
