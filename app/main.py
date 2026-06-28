import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.bot.telegram_webhook import (
    build_webhook_url,
    delete_webhook,
    is_telegram_configured,
    process_telegram_update,
    set_webhook,
    shutdown_telegram_application,
)
from app.config import get_settings
from app.database import get_db
from app.schemas.search import SearchResponse
from app.services.privacy_log import mask_query_for_log
from app.services.search_service import SearchService
from app.sources.health import get_sources_health

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await shutdown_telegram_application()


app = FastAPI(
    title="Bot TL - Desaparecidos",
    description="Backend para búsqueda de personas en listas públicas de desaparecidos",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)


class SetWebhookRequest(BaseModel):
    webhook_url: str | None = None


def _verify_admin_secret(request: Request) -> None:
    current = get_settings()
    if not current.admin_secret:
        raise HTTPException(status_code=404, detail="No encontrado")
    provided = request.headers.get("X-Admin-Secret")
    if not provided or provided != current.admin_secret:
        raise HTTPException(status_code=403, detail="No autorizado")


@app.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception:
        logger.exception("Health check: fallo conexión a base de datos")
        raise HTTPException(
            status_code=503,
            detail={"status": "error", "database": "disconnected"},
        ) from None


@app.get("/sources/health")
def sources_health() -> dict:
    return get_sources_health()


@app.get("/search", response_model=SearchResponse)
def search_people(
    q: str = Query(..., min_length=1, description="Nombre o cédula (solo números)"),
    db: Session = Depends(get_db),
) -> SearchResponse:
    try:
        service = SearchService(db)
        return service.search(q)
    except ValueError as exc:
        logger.warning("Consulta inválida q=%s: %s", mask_query_for_log(q), exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("Error en búsqueda q=%s", mask_query_for_log(q))
        raise HTTPException(status_code=500, detail="Error interno al buscar") from None


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict[str, bool]:
    try:
        update_data: dict[str, Any] = await request.json()
        await process_telegram_update(update_data)
    except Exception:
        logger.exception("Error procesando webhook de Telegram")
    return {"ok": True}


@app.get("/telegram/status")
def telegram_status() -> dict[str, bool | str]:
    return {
        "mode": "webhook",
        "configured": is_telegram_configured(),
    }


@app.post("/admin/telegram/set-webhook")
def admin_set_webhook(
    request: Request,
    body: SetWebhookRequest = SetWebhookRequest(),
) -> dict[str, Any]:
    _verify_admin_secret(request)
    webhook_url = body.webhook_url or build_webhook_url()
    logger.info("Admin: configurando webhook de Telegram")
    result = set_webhook(webhook_url)
    return {"ok": True, "webhook_url": webhook_url, "result": result}


@app.post("/admin/telegram/delete-webhook")
def admin_delete_webhook(request: Request) -> dict[str, Any]:
    _verify_admin_secret(request)
    logger.info("Admin: eliminando webhook de Telegram")
    result = delete_webhook()
    return {"ok": True, "result": result}
