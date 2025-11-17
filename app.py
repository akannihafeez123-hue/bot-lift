# app.py
from fastapi import FastAPI, Request, HTTPException
import httpx
import asyncio
import logging
import os

app = FastAPI()
LOG = logging.getLogger("seed_webhook")
logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID")) if os.environ.get("ADMIN_CHAT_ID") else None
TELEGRAM_API = "https://api.telegram.org"

async def send_telegram_message(chat_id: int, text: str):
    if not TELEGRAM_TOKEN:
        LOG.warning("TELEGRAM_TOKEN not set; cannot send message: %s", text)
        return
    url = f"{TELEGRAM_API}/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})

# Replace this stub with your real evaluate_symbol/orchestrator
def evaluate_symbol(symbol: str):
    score = (sum(ord(c) for c in symbol) % 100) / 100.0
    return {
        "symbol": symbol,
        "hotness": round(score, 3),
        "strategies": {"demo": round(score, 3)},
        "survivability": {"1m": round(score, 3), "2m": round(score * 0.7, 3), "3m": round(score * 0.5, 3)},
    }

@app.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request):
    # require token in path as a simple validation
    if token != TELEGRAM_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")
    update = await request.json()
    msg = update.get("message") or update.get("edited_message") or {}
    text = (msg.get("text") or "").strip()
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if not text or not chat_id:
        return {"ok": True}

    # keep /start welcome
    if text.lower().startswith("/start"):
        await send_telegram_message(chat_id, "Welcome! Bot is live on Seed. Use /scan SYMBOL (admin only).")
        return {"ok": True}

    # admin-only /scan
    if text.lower().startswith("/scan"):
        parts = text.split()
        if len(parts) < 2:
            await send_telegram_message(chat_id, "Usage: /scan SYMBOL (admin only)")
            return {"ok": True}
        if ADMIN_CHAT_ID is not None and chat_id != ADMIN_CHAT_ID:
            await send_telegram_message(chat_id, "Permission denied. Admins only.")
            return {"ok": True}
        symbol = parts[1].upper()
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, evaluate_symbol, symbol)
            text_out = f"*{result['symbol']}* HOTNESS: *{result['hotness']}*\n"
            text_out += "Strategies: " + ", ".join([f"{k}:{v}" for k, v in result.get("strategies", {}).items()])
            await send_telegram_message(chat_id, text_out)
        except Exception:
            LOG.exception("Scan failed")
            await send_telegram_message(chat_id, "Scan failed (see logs)")
        return {"ok": True}

    return {"ok": True}

@app.post("/scan/{token}")
async def http_scan_trigger(token: str, request: Request):
    if token != TELEGRAM_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")
    body = await request.json()
    symbol = body.get("symbol")
    reply_to = body.get("reply_to") or ADMIN_CHAT_ID
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol required")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, evaluate_symbol, symbol.upper())
    text_out = f"*{result['symbol']}* HOTNESS: *{result['hotness']}*\n"
    text_out += "Strategies: " + ", ".join([f"{k}:{v}" for k, v in result.get("strategies", {}).items()])
    await send_telegram_message(reply_to, text_out)
    return {"ok": True, "result": result}
