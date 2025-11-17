from fastapi import FastAPI, Request
import httpx
import asyncio
import logging
import os

# Try to load config.py if you already have it on Botlify
TELEGRAM_TOKEN = None
ADMIN_CHAT_ID = None
try:
    import config as _cfg
    TELEGRAM_TOKEN = getattr(_cfg, "TELEGRAM_TOKEN", None)
    ADMIN_CHAT_ID = getattr(_cfg, "ADMIN_CHAT_ID", None)
except Exception:
    pass

# Fallback to environment variable (Botlify might expose this)
if not TELEGRAM_TOKEN:
    TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Try admin id from environment too
if ADMIN_CHAT_ID is None:
    admin_env = os.environ.get("ADMIN_CHAT_ID")
    if admin_env:
        try:
            ADMIN_CHAT_ID = int(admin_env)
        except Exception:
            ADMIN_CHAT_ID = None

app = FastAPI()
LOG = logging.getLogger("botlify_webhook")
logging.basicConfig(level=logging.INFO)

TELEGRAM_API = "https://api.telegram.org"

async def send_telegram_message(chat_id: int, text: str):
    if not TELEGRAM_TOKEN:
        LOG.warning("TELEGRAM_TOKEN not set; cannot send message: %s", text)
        return
    url = f"{TELEGRAM_API}/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
        except Exception:
            LOG.exception("Failed sending message")

# Replace this with your real evaluate_symbol/orchestrator when ready
def evaluate_symbol(symbol: str):
    score = (sum(ord(c) for c in symbol) % 100) / 100.0
    return {"symbol": symbol, "hotness": round(score, 3), "strategies": {"demo": round(score, 3)}}

@app.post("/")
async def handle_update(request: Request):
    """
    Botlify usually posts Telegram updates to the root path. This handler:
    - replies to /start with a welcome (keeps your old welcome behavior),
    - handles admin-only /scan SYMBOL.
    """
    update = await request.json()
    msg = update.get("message") or update.get("edited_message") or {}
    text = (msg.get("text") or "").strip()
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    user = msg.get("from") or {}

    if not text or not chat_id:
        return {"ok": True}

    # keep the welcome behavior
    if text.lower().startswith("/start"):
        welcome = "Welcome! This bot is connected and ready. Use /scan SYMBOL (admin only)."
        await send_telegram_message(chat_id, welcome)
        return {"ok": True}

    # admin-only /scan command
    if text.lower().startswith("/scan"):
        parts = text.split()
        if len(parts) < 2:
            await send_telegram_message(chat_id, "Usage: /scan SYMBOL (admin only)")
            return {"ok": True}
        # If ADMIN_CHAT_ID is set, restrict to it. If not set, allow the user who started the bot (best-effort).
        if ADMIN_CHAT_ID is not None and chat_id != ADMIN_CHAT_ID:
            await send_telegram_message(chat_id, "Permission denied. Admins only.")
            return {"ok": True}
        symbol = parts[1].upper()
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, evaluate_symbol, symbol)
            if result:
                text_out = f"*{result['symbol']}* HOTNESS: *{result['hotness']}*\n"
                text_out += "Strategies: " + ", ".join([f"{k}:{v}" for k, v in result.get("strategies", {}).items()])
            else:
                text_out = f"No result for {symbol}"
            await send_telegram_message(chat_id, text_out)
        except Exception:
            LOG.exception("Scan failed")
            await send_telegram_message(chat_id, "Scan failed (see logs)")
        return {"ok": True}

    # If you had other handlers in the welcome code, add them here.

    return {"ok": True}
