import os, re, asyncio
from typing import Optional
import httpx
import pandas as pd
from fastapi import FastAPI, Request, HTTPException

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
PUBLIC_URL = os.getenv('PUBLIC_URL', '').rstrip('/')
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', '').strip()
BINANCE_BASE = 'https://api.binance.com'
INTERVALS = {'5m','15m','1h','4h','1d'}
SYMBOL_RE = re.compile(r'^[A-Z0-9]{5,20}$')

app = FastAPI(title='WayffreedBot', version='1.0.0')

async def tg(method: str, payload: dict):
    if not BOT_TOKEN:
        raise RuntimeError('TELEGRAM_BOT_TOKEN is not configured')
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f'https://api.telegram.org/bot{BOT_TOKEN}/{method}', json=payload)
        r.raise_for_status()
        return r.json()

async def market_json(path: str, params: dict):
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(BINANCE_BASE + path, params=params)
        r.raise_for_status()
        return r.json()

def indicators(rows):
    cols = ['open_time','open','high','low','close','volume','close_time','qav','trades','tbbav','tbqav','ignore']
    df = pd.DataFrame(rows, columns=cols)
    for c in ['open','high','low','close','volume']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    close = df['close']
    df['ema20'] = close.ewm(span=20, adjust=False).mean()
    df['ema50'] = close.ewm(span=50, adjust=False).mean()
    df['ema200'] = close.ewm(span=200, adjust=False).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, pd.NA)
    df['rsi'] = 100 - (100 / (1 + rs.astype('float64')))
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    prev_close = close.shift(1)
    tr = pd.concat([(df['high']-df['low']), (df['high']-prev_close).abs(), (df['low']-prev_close).abs()], axis=1).max(axis=1)
    df['atr'] = tr.ewm(alpha=1/14, adjust=False).mean()
    return df

def fmt_price(x):
    if x >= 1000: return f'{x:,.2f}'
    if x >= 1: return f'{x:,.4f}'
    return f'{x:,.8f}'

async def analyze(symbol: str, interval: str):
    rows = await market_json('/api/v3/klines', {'symbol': symbol, 'interval': interval, 'limit': 250})
    df = indicators(rows)
    x = df.iloc[-1]
    score = 0
    reasons = []
    if x.close > x.ema20: score += 1; reasons.append('price above EMA20')
    else: score -= 1; reasons.append('price below EMA20')
    if x.ema20 > x.ema50: score += 2; reasons.append('EMA20 above EMA50')
    else: score -= 2; reasons.append('EMA20 below EMA50')
    if x.ema50 > x.ema200: score += 2; reasons.append('EMA50 above EMA200')
    else: score -= 2; reasons.append('EMA50 below EMA200')
    if x.macd > x.signal: score += 1; reasons.append('MACD bullish')
    else: score -= 1; reasons.append('MACD bearish')
    if 50 <= x.rsi <= 70: score += 1; reasons.append('RSI supports bullish momentum')
    elif 30 <= x.rsi < 50: score -= 1; reasons.append('RSI shows weaker momentum')
    elif x.rsi > 70: score -= 1; reasons.append('RSI is overbought')
    else: score += 1; reasons.append('RSI is oversold; reversal possible')
    if score >= 5: signal = '🟢 BUY BIAS'
    elif score <= -5: signal = '🔴 SELL BIAS'
    else: signal = '🟡 HOLD / WAIT'
    recent = df.tail(50)
    support = recent.low.min()
    resistance = recent.high.max()
    atr = float(x.atr)
    entry = float(x.close)
    if 'BUY' in signal:
        stop, target = entry - 1.5*atr, entry + 3*atr
    elif 'SELL' in signal:
        stop, target = entry + 1.5*atr, entry - 3*atr
    else:
        stop = target = None
    return {
        'price': entry, 'rsi': float(x.rsi), 'macd': float(x.macd), 'macd_signal': float(x.signal),
        'ema20': float(x.ema20), 'ema50': float(x.ema50), 'ema200': float(x.ema200), 'atr': atr,
        'support': float(support), 'resistance': float(resistance), 'score': score, 'signal': signal,
        'stop': stop, 'target': target, 'reasons': reasons
    }

async def send(chat_id: int, text: str):
    return await tg('sendMessage', {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True})

def help_text():
    return ('🤖 WayffreedBot\n\n'
            'Crypto market analysis powered by technical indicators.\n\n'
            'Commands:\n'
            '/price BTCUSDT — current price\n'
            '/analyze BTCUSDT 1h — full analysis\n'
            '/signal BTCUSDT 1h — quick signal\n'
            '/markets — supported examples\n'
            '/help — show help\n\n'
            '⚠️ Educational market analysis only. Not financial advice and not a guarantee of profit.')

@app.get('/')
async def root():
    return {'bot':'WayffreedBot','status':'online'}

@app.get('/health')
async def health():
    return {'status':'ok'}

@app.on_event('startup')
async def startup():
    if BOT_TOKEN and PUBLIC_URL and WEBHOOK_SECRET:
        await tg('setWebhook', {'url': f'{PUBLIC_URL}/webhook/{WEBHOOK_SECRET}', 'drop_pending_updates': True})

@app.post('/webhook/{secret}')
async def webhook(secret: str, request: Request):
    if not WEBHOOK_SECRET or secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail='Forbidden')
    update = await request.json()
    msg = update.get('message') or update.get('edited_message')
    if not msg or 'chat' not in msg or 'text' not in msg:
        return {'ok': True}
    chat_id = msg['chat']['id']
    text = msg['text'].strip()
    parts = text.split()
    cmd = parts[0].split('@')[0].lower() if parts else ''
    try:
        if cmd in ('/start','/help'):
            await send(chat_id, help_text())
        elif cmd == '/markets':
            await send(chat_id, 'Examples: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, ADAUSDT\n\nUse /analyze SYMBOL 1h')
        elif cmd == '/price':
            symbol = parts[1].upper() if len(parts) > 1 else 'BTCUSDT'
            if not SYMBOL_RE.fullmatch(symbol): raise ValueError('Invalid symbol')
            ticker = await market_json('/api/v3/ticker/24hr', {'symbol': symbol})
            await send(chat_id, f'💰 {symbol}\nPrice: {fmt_price(float(ticker["lastPrice"]))}\n24h: {float(ticker["priceChangePercent"]):+.2f}%')
        elif cmd in ('/analyze','/signal'):
            symbol = parts[1].upper() if len(parts) > 1 else 'BTCUSDT'
            interval = parts[2].lower() if len(parts) > 2 else '1h'
            if not SYMBOL_RE.fullmatch(symbol): raise ValueError('Invalid symbol')
            if interval not in INTERVALS: raise ValueError('Interval must be 5m, 15m, 1h, 4h or 1d')
            a = await analyze(symbol, interval)
            if cmd == '/signal':
                msgout = (f'📊 {symbol} • {interval}\n\n{a["signal"]}\n'
                          f'Score: {a["score"]:+d}/10\nRSI: {a["rsi"]:.1f}\nPrice: {fmt_price(a["price"])}\n\n'
                          '⚠️ Technical bias only — not financial advice.')
            else:
                msgout = (f'📊 WAYFFREEDBOT ANALYSIS\n{symbol} • {interval}\n\n'
                          f'{a["signal"]}\nTechnical score: {a["score"]:+d}/10\n\n'
                          f'Price: {fmt_price(a["price"])}\nRSI(14): {a["rsi"]:.1f}\n'
                          f'EMA20: {fmt_price(a["ema20"])}\nEMA50: {fmt_price(a["ema50"])}\nEMA200: {fmt_price(a["ema200"])}\n'
                          f'MACD: {a["macd"]:.6f}\nSupport: {fmt_price(a["support"])}\nResistance: {fmt_price(a["resistance"])}\n'
                          f'ATR(14): {fmt_price(a["atr"])}\n')
                if a['stop'] is not None:
                    msgout += f'\nIllustrative stop: {fmt_price(a["stop"])}\nIllustrative target: {fmt_price(a["target"])}\n'
                msgout += '\nWhy: ' + ', '.join(a['reasons']) + '.\n\n⚠️ Educational technical analysis only. No guaranteed results.'
            await send(chat_id, msgout)
        else:
            await send(chat_id, 'I did not recognize that command. Try /help')
    except httpx.HTTPStatusError as e:
        await send(chat_id, 'I could not fetch that market right now. Check the symbol and try again.')
    except Exception as e:
        await send(chat_id, f'⚠️ {str(e)}')
    return {'ok': True}
