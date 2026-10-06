# WayffreedBot

Simple Telegram cryptocurrency market-analysis bot using FastAPI and Binance public market data.

## Render

Build command:
`pip install -r requirements.txt`

Start command:
`uvicorn main:app --host 0.0.0.0 --port $PORT`

Environment variable:
`TELEGRAM_BOT_TOKEN=YOUR_BOTFATHER_TOKEN`

Never publish the Telegram token in GitHub or send it in chat.

Test the deployed service by opening `/` or `/health`.

This starter version focuses on a stable deployment first. Advanced indicators, multi-timeframe analysis, alerts, watchlists and improved signal scoring can be added after the basic bot is running.

Trading involves risk; the bot does not guarantee profits.
