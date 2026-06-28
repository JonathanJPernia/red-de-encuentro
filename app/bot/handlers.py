import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.bot.rate_limit import InMemoryRateLimiter
from app.bot.response_format import format_search_response
from app.database import SessionLocal
from app.services.privacy_log import mask_query_for_log
from app.services.query_validation import validate_search_query
from app.services.search_service import BOT_MAX_RESULTS, SearchService
from app.services.status_labels import INFORMATIONAL_DISCLAIMER

logger = logging.getLogger(__name__)

DISCLAIMER = f"\n\n{INFORMATIONAL_DISCLAIMER}"

RATE_LIMIT_MESSAGE = (
    "Has hecho muchas búsquedas seguidas. Intenta de nuevo en unos minutos."
)

telegram_rate_limiter = InMemoryRateLimiter(max_calls=10, period_seconds=300)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hola. Puedo ayudarte a buscar personas en listas públicas de desaparecidos.\n\n"
        f"{INFORMATIONAL_DISCLAIMER}\n\n"
        "Para emergencias, contacta autoridades locales oficiales.\n\n"
        "Envíame un mensaje con:\n"
        "• Un nombre completo o parcial (ej: Juan Pérez)\n"
        "• Un número de cédula (ej: 12345678, V-12345678, 12.345.678)\n\n"
        "Nunca compartas datos sensibles innecesarios."
    )


async def handle_text_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    query = update.message.text.strip()
    user = update.effective_user
    user_key = str(user.id if user else update.effective_chat.id)

    if not telegram_rate_limiter.is_allowed(user_key):
        logger.warning("Rate limit excedido user=%s", user_key)
        await update.message.reply_text(RATE_LIMIT_MESSAGE)
        return

    if not query:
        await update.message.reply_text("Envía un nombre o número de cédula para buscar.")
        return

    try:
        validate_search_query(query)
    except ValueError as exc:
        logger.info("Consulta inválida user=%s q=%s", user_key, mask_query_for_log(query))
        await update.message.reply_text(str(exc))
        return

    db = SessionLocal()
    try:
        service = SearchService(db)
        response = service.search(query, limit=BOT_MAX_RESULTS)
        logger.info(
            "Búsqueda telegram user=%s q=%s resultados=%d",
            user_key,
            mask_query_for_log(query),
            len(response.matches),
        )

        if not response.matches:
            await update.message.reply_text(
                "No encontré coincidencias en las fuentes cargadas hasta ahora."
                + DISCLAIMER
            )
            return

        await update.message.reply_text(format_search_response(response.matches))
    except ValueError as exc:
        logger.warning(
            "Consulta inválida user=%s q=%s: %s",
            user_key,
            mask_query_for_log(query),
            exc,
        )
        await update.message.reply_text(str(exc))
    except Exception:
        logger.exception("Error inesperado en búsqueda user=%s q=%s", user_key, mask_query_for_log(query))
        await update.message.reply_text(
            "Ocurrió un error al buscar. Intenta de nuevo en unos momentos."
        )
    finally:
        db.close()


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_search))
