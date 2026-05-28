# StickerNow (Telegram MVP)

Telegram-first glowing sticker bot: **[@stickernow_bot](https://t.me/stickernow_bot)**. Core effect: **remove background** from the main subject, then **apply a neon glow**. Users stay inside Telegram for upload, glow edit (Mini App), **Telegram Stars (XTR)** payment, and delivery.

No Stripe, cards, TON/USDT checkout, or external payment site in this MVP.

## Product flow

1. Open bot → `/start`
2. Send a photo (one clear subject)
3. Background removed automatically
4. Pick glow color → one glowing sticker (1 credit)
5. Tweak glow / outline in Mini App
6. Deliver Telegram-ready stickers
7. Buy credits with Stars if needed (`/buy`)

## Credits & packages

Configured in `src/config.py` (prices in **Stars**, not RUB):

| Package   | Credits | Stars |
|-----------|---------|-------|
| pack_1    | 1       | 50    |
| pack_10   | 10      | 400   |

1 credit = 1 photo → 1 sticker.

## Payments (Telegram Stars)

- `send_invoice` with `currency="XTR"` and empty `provider_token`
- `pre_checkout_query` → signed payload + amount validation → `answerPreCheckoutQuery`
- `successful_payment` → store `telegram_payment_charge_id`, idempotent credit grant
- `/paysupport` for payment help
- Admin `/refund <user_id> <charge_id>` → `refundStarPayment`

Enable payments for your bot in [@BotFather](https://t.me/BotFather) (Bot Settings → Payments).

## Quick start (Windows)

**First time:** double-click `install.bat` (or run it in a terminal), then edit `.env` with your `BOT_TOKEN`.

**Every time:** double-click `run.bat` — or in PowerShell:

```powershell
cd "c:\Users\DELL\cursor_projects\Sticker app"
.\run.ps1
```

## Setup (manual)

```bash
cd "Sticker app"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env`:

- `BOT_TOKEN` — from BotFather (**never commit**; rotate if leaked)
- `BOT_SECRET` — random string for invoice payload HMAC
- `ADMIN_TELEGRAM_IDS` — your numeric Telegram user id for refunds
- `MINI_APP_URL` — public HTTPS URL to `/miniapp/` (use [ngrok](https://ngrok.com) locally)

Register the Mini App URL in BotFather (Menu Button or Web App).

Run:

```bash
python -m src.main
```

Static Mini App is served on `http://127.0.0.1:8080/miniapp/` for local dev; production needs HTTPS.

## Security

If the bot token was shared in chat or logs, revoke it in BotFather (`/revoke`) and set a new token in `.env`.

## Image processing (background removal first)

1. **Background removal** (in order):
   - **rembg** — local, free, keeps your original photo pixels (`REMOVE_BG_ENABLED=true`)
   - **remove.bg** — optional API for difficult photos (`REMOVE_BG_API_KEY`)
   - **OpenAI** — last resort only; strict “remove background, don’t change the subject” prompt (`AI_API_KEY`)
2. **Glow** — `src/services/glow.py` (Pillow blur + outline)

For stickers, faithful cutout matters more than AI “enhancement.” **rembg is the main engine**; APIs are backups.

### Optional `.env` for harder photos

```env
# Best dedicated BG removal (paid per image)
REMOVE_BG_API_KEY=your-remove-bg-key

# Last resort if rembg + remove.bg fail (paid; can subtly alter details)
AI_API_KEY=sk-...
AI_BG_FALLBACK_ENABLED=true
```

You do **not** need OpenAI for normal BG removal — `pip install "rembg[cpu]"` is enough.

## Later (out of scope)

- Stripe / web checkout
- Direct TON/USDT user payments
- Withdrawing Stars → TON via Telegram’s supported flows (business ops, not user checkout)
