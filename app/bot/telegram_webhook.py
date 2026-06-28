from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from telegram import Update
from telegram.ext import Application

from app.bot.handlers import register_handlers
from app.config import get_settings

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"

_application: Application | None = None
_application_ready = False
_application_lock = asyncio.Lock()


def create_telegram_application() -> Application:
    settings = get_settings()
    application = Application.builder().token(settings.telegram_bot_token).build()
    register_handlers(application)
    return application


async def _ensure_application_ready() -> Application:
    global _application, _application_ready

    async with _application_lock:
        if _application is None:
            _application = create_telegram_application()
        if not _application_ready:
            await _application.initialize()
            await _application.start()
            _application_ready = True

    return _application


async def shutdown_telegram_application() -> None:
    global _application, _application_ready

    async with _application_lock:
        if _application is None or not _application_ready:
            return
        await _application.stop()
        await _application.shutdown()
        _application = None
        _application_ready = False


async def process_telegram_update(update_data: dict[str, Any]) -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("Webhook recibido pero TELEGRAM_BOT_TOKEN no está configurado")
        return

    application = await _ensure_application_ready()
    update = Update.de_json(update_data, application.bot)
    await application.process_update(update)


def build_webhook_url(base_url: str | None = None) -> str:
    settings = get_settings()
    public_base = (base_url or settings.public_base_url).strip().rstrip("/")
    if not public_base:
        raise ValueError("PUBLIC_BASE_URL no está configurado")
    return f"{public_base}/telegram/webhook"


def _telegram_api(method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN no está configurado")

    url = TELEGRAM_API_BASE.format(token=settings.telegram_bot_token, method=method)
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, json=payload or {})
        response.raise_for_status()
        data = response.json()

    if not data.get("ok"):
        description = data.get("description", "respuesta inválida de Telegram")
        raise RuntimeError(f"Telegram API {method} falló: {description}")

    return data


def set_webhook(webhook_url: str) -> dict[str, Any]:
    logger.info("Configurando webhook de Telegram")
    return _telegram_api("setWebhook", {"url": webhook_url})


def delete_webhook() -> dict[str, Any]:
    logger.info("Eliminando webhook de Telegram")
    return _telegram_api("deleteWebhook", {})


def is_telegram_configured() -> bool:
    settings = get_settings()
    return bool(settings.telegram_bot_token)
