# WayffreedBot — v1 Crypto Analysis

A Telegram bot backend for `@wayffreedbot` using Binance public market data and technical indicators.

## Included
- `/start`, `/help`
- `/price BTCUSDT`
- `/signal BTCUSDT 1h`
- `/analyze BTCUSDT 1h`
- `/markets`
- EMA 20/50/200, RSI(14), MACD, ATR, support/resistance
- Technical BUY/SELL/HOLD bias with an explanatory score
- Telegram webhook via FastAPI
- No trading API key required for market-data-only operation

## Deploy on Render
1. Put this folder into a GitHub repository.
2. In Render, choose **New → Web Service**, connect the repository.
3. Build: `pip install -r requirements.txt`
4. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Choose the Free plan for testing.
6. Add environment variables:
   - `TELEGRAM_BOT_TOKEN` = your private BotFather token
   - `PUBLIC_URL` = your Render HTTPS URL
   - `WEBHOOK_SECRET` = a long random secret
7. Deploy. On startup the app automatically registers the Telegram webhook.

IMPORTANT: Never paste your BotFather token into chat, GitHub, screenshots, or this repository. Store it only as a secret/environment variable in Render.

## Notes
Render free web services can spin down after inactivity, so this v1 is intended for testing/prototyping. Upgrade later if you need continuous production availability.

This bot provides technical analysis for educational purposes. It does not execute trades and does not guarantee profits.
