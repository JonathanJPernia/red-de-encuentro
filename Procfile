# Railway: crear un servicio por proceso y usar el comando correspondiente.
# API web:
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT

# Worker del bot Telegram (servicio separado):
worker: python -m app.bot.telegram_bot
