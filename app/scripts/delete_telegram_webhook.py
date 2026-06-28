"""Elimina el webhook de Telegram (vuelve a modo sin webhook remoto)."""

from app.bot.telegram_webhook import delete_webhook
from app.config import get_settings


def main() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN no está configurado")

    result = delete_webhook()
    print("Webhook eliminado")
    print(result)


if __name__ == "__main__":
    main()
