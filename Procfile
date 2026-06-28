# Railway / Render: solo API en producción (webhook Telegram).
# worker: solo desarrollo local con polling
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
worker: python -m app.bot.telegram_bot
