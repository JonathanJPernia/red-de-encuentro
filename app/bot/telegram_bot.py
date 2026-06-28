"""
Bot de Telegram en modo polling (solo desarrollo local).

En producción (Render) usar webhook vía FastAPI:
    POST /telegram/webhook
"""

import logging

from app.bot.telegram_webhook import create_telegram_application
from app.config import get_settings

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN no está configurado en .env")

    application = create_telegram_application()

    logger.info("Bot de Telegram iniciado en modo polling (solo local)")
    application.run_polling()


if __name__ == "__main__":
    main()
