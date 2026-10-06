import os
from typing import Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="WayffreedBot", version="1.0.0")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
BINANCE_BASE_URL = "https://api.binance.com"


async def binance_get(path: str, params: Optional[dict] = None):
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(BINANCE_BASE_URL + path, params=params)
        response.raise_for_status()
        return response.json()


async def telegram_send_message(chat_id: int, text: str):
    if not TELEGRAM_BOT_TOKEN:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(url, json={"chat_id": chat_id, "text": text})


@app.get("/")
async def home():
    return {"status": "online", "bot": "WayffreedBot"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    update = await request.json()
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "").strip()

    if not chat_id or not text:
        return JSONResponse({"ok": True})

    if text.startswith("/start"):
        reply = (
            "🤖 Welcome to WayffreedBot!\n\n"
            "Use /help to see commands.\n\n"
            "⚠️ Educational information only. Trading involves risk."
        )
    elif text.startswith("/help"):
        reply = (
            "📚 WayffreedBot Commands\n\n"
            "/start - Start the bot\n"
            "/help - Show help\n"
            "/price BTCUSDT - Current price\n"
            "/analyze BTCUSDT - Basic analysis\n"
            "/markets - Supported examples"
        )
    elif text.startswith("/markets"):
        reply = "📊 Examples: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT"
    elif text.startswith("/price"):
        parts = text.split()
        symbol = parts[1].upper() if len(parts) > 1 else "BTCUSDT"
        try:
            data = await binance_get("/api/v3/ticker/price", {"symbol": symbol})
            reply = f"💰 {symbol}\nCurrent price: ${float(data['price']):,.4f}"
        except Exception:
            reply = f"❌ Could not retrieve {symbol}. Check the symbol."
    elif text.startswith("/analyze"):
        parts = text.split()
        symbol = parts[1].upper() if len(parts) > 1 else "BTCUSDT"
        try:
            data = await binance_get("/api/v3/ticker/24hr", {"symbol": symbol})
            change = float(data["priceChangePercent"])
            bias = "Bullish" if change > 1 else "Bearish" if change < -1 else "Neutral"
            reply = (
                f"📊 {symbol} — Basic Analysis\n\n"
                f"Price: ${float(data['lastPrice']):,.4f}\n"
                f"24h Change: {change:+.2f}%\n"
                f"24h Volume: ${float(data['quoteVolume']):,.0f}\n"
                f"Technical Bias: {bias}\n\n"
                "⚠️ This is not a guaranteed prediction or financial advice."
            )
        except Exception:
            reply = f"❌ Could not analyze {symbol}. Check the symbol."
    else:
        reply = "I didn't recognize that command. Type /help."

    await telegram_send_message(chat_id, reply)
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
