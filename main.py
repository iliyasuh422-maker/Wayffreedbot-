import os
from typing import Optional
import httpx
import numpy as np
from fastapi import FastAPI, Request, HTTPException

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
PUBLIC_URL = os.getenv("PUBLIC_URL", "").strip().rstrip("/")
SECRET = os.getenv("WEBHOOK_SECRET", "wayffreed-webhook").strip()
app = FastAPI(title="WayffreedBot")
BINANCE = "https://api.binance.com"

async def tg(method, payload):
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"https://api.telegram.org/bot{TOKEN}/{method}", json=payload)
        r.raise_for_status()
        return r.json()

async def send(chat_id, text):
    return await tg("sendMessage", {"chat_id": chat_id, "text": text})

async def price(symbol):
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{BINANCE}/api/v3/ticker/price", params={"symbol": symbol.upper()})
        r.raise_for_status()
        return float(r.json()["price"])

async def klines(symbol, interval="1h"):
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{BINANCE}/api/v3/klines",
                         params={"symbol": symbol.upper(), "interval": interval, "limit": 250})
        r.raise_for_status()
        return r.json()

def ema(x, n):
    x = np.asarray(x, float)
    a = 2/(n+1)
    y = np.empty(len(x)); y[0] = x[0]
    for i in range(1, len(x)): y[i] = a*x[i] + (1-a)*y[i-1]
    return y

def rsi(x, n=14):
    d = np.diff(np.asarray(x, float))
    g, l = np.maximum(d,0), np.maximum(-d,0)
    ag, al = g[:n].mean(), l[:n].mean()
    for i in range(n, len(d)):
        ag = ((n-1)*ag + g[i])/n
        al = ((n-1)*al + l[i])/n
    return 100 if al == 0 else 100 - 100/(1+ag/al)

def analysis(rows):
    c = np.array([float(r[4]) for r in rows])
    e20, e50, e200 = ema(c,20)[-1], ema(c,50)[-1], ema(c,200)[-1]
    rv = rsi(c)
    m = ema(c,12) - ema(c,26)
    macd, sig = m[-1], ema(m,9)[-1]
    score = (1 if c[-1]>e20 else -1) + (1 if e20>e50 else -1) + (1 if e50>e200 else -1)
    score += 1 if rv >= 50 else -1
    score += 1 if macd > sig else -1
    bias = "BUY" if score >= 3 else "SELL" if score <= -3 else "HOLD"
    return c[-1], e20, e50, e200, rv, macd, sig, score, bias

def args(text):
    p = text.split()
    return (p[1].upper() if len(p)>1 else "BTCUSDT",
            p[2] if len(p)>2 else "1h")

async def command(chat_id, text):
    cmd = text.split()[0].lower()
    if cmd == "/start":
        return await send(chat_id, "🤖 Welcome to WayffreedBot!\n\n/price BTCUSDT\n/signal BTCUSDT 1h\n/analyze BTCUSDT 1h\n/markets\n/help\n\n⚠️ Educational analysis only.")
    if cmd == "/help":
        return await send(chat_id, "📚 Commands:\n/price BTCUSDT\n/signal BTCUSDT 1h\n/analyze BTCUSDT 1h\n/markets\n\nIntervals: 5m, 15m, 1h, 4h, 1d.")
    if cmd == "/markets":
        return await send(chat_id, "📊 Examples:\nBTCUSDT\nETHUSDT\nBNBUSDT\nSOLUSDT\nXRPUSDT\nDOGEUSDT")
    if cmd == "/price":
        s,_ = args(text); p = await price(s)
        return await send(chat_id, f"💰 {s}\nCurrent price: {p:,.6f} USDT")
    if cmd in ("/signal","/analyze"):
        s,iv = args(text)
        allowed = {"5m","15m","1h","4h","1d"}
        if iv not in allowed: iv="1h"
        a = analysis(await klines(s,iv))
        msg = (f"📈 {s} — {iv}\n\nSignal: {a[8]}\nScore: {a[7]}\nPrice: {a[0]:,.6f} USDT\n"
               f"EMA20: {a[1]:,.6f}\nEMA50: {a[2]:,.6f}\nEMA200: {a[3]:,.6f}\nRSI: {a[4]:.1f}\n"
               f"MACD: {a[5]:.6f}\nSignal line: {a[6]:.6f}\n\n⚠️ Educational analysis only; not financial advice.")
        return await send(chat_id, msg)
    return await send(chat_id, "Unknown command. Send /help.")

@app.get("/")
async def health():
    return {"status":"ok","service":"WayffreedBot"}

@app.post("/telegram/{secret}")
async def webhook(request: Request, secret: str):
    if secret != SECRET: raise HTTPException(403, "Invalid webhook secret")
    u = await request.json()
    m = u.get("message") or u.get("edited_message")
    if m and m.get("chat",{}).get("id") and m.get("text","").startswith("/"):
        try: await command(m["chat"]["id"], m["text"])
        except Exception as e: await send(m["chat"]["id"], f"❌ Error: {str(e)[:250]}")
    return {"ok":True}

@app.on_event("startup")
async def startup():
    if not TOKEN or not PUBLIC_URL:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and PUBLIC_URL must be set")
    await tg("setWebhook", {"url": f"{PUBLIC_URL}/telegram/{SECRET}", "drop_pending_updates": True})
