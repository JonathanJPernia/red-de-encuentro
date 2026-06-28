"""Registra el webhook de Telegram apuntando a PUBLIC_BASE_URL/telegram/webhook."""

from app.bot.telegram_webhook import build_webhook_url, set_webhook
from app.config import get_settings


def main() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN no está configurado")
    if not settings.public_base_url:
        raise SystemExit("PUBLIC_BASE_URL no está configurado")

    webhook_url = build_webhook_url()
    result = set_webhook(webhook_url)
    print(f"Webhook configurado: {webhook_url}")
    print(result)


if __name__ == "__main__":
    main()
