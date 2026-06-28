import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.admin_auth import verify_admin_secret
from app.admin_dashboard import render_admin_dashboard_html
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
from app.services.analytics_service import get_admin_stats, log_search
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


def _client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    return request.client.host


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


@app.get("/search", response_model=SearchResponse, response_model_exclude_none=True)
def search_people(
    request: Request,
    q: str = Query(..., min_length=1, description="Nombre o cédula (solo números)"),
    debug: bool = Query(default=False, description="Stats por fuente (requiere ADMIN_SECRET)"),
    db: Session = Depends(get_db),
) -> SearchResponse:
    started = time.perf_counter()
    client_ip = _client_ip(request)
    include_debug = False
    if debug:
        verify_admin_secret(request)
        include_debug = True

    def _elapsed_ms() -> int:
        return int((time.perf_counter() - started) * 1000)

    try:
        service = SearchService(db)
        response = service.search(q, include_debug=include_debug)
        log_search(
            db,
            source="api",
            query=q,
            results_count=len(response.matches),
            response_ms=_elapsed_ms(),
            success=True,
            user_identifier=client_ip,
        )
        return response
    except ValueError as exc:
        log_search(
            db,
            source="api",
            query=q,
            results_count=0,
            response_ms=_elapsed_ms(),
            success=False,
            error_type="validation_error",
            user_identifier=client_ip,
        )
        logger.warning("Consulta inválida q=%s: %s", mask_query_for_log(q), exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        log_search(
            db,
            source="api",
            query=q,
            results_count=0,
            response_ms=_elapsed_ms(),
            success=False,
            error_type="internal_error",
            user_identifier=client_ip,
        )
        logger.exception("Error en búsqueda q=%s", mask_query_for_log(q))
        raise HTTPException(status_code=500, detail="Error interno al buscar") from None


@app.get("/admin/stats")
def admin_stats(
    request: Request,
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    verify_admin_secret(request)
    logger.info("Admin: consulta de analytics days=%s", days)
    return get_admin_stats(db, days=days)


@app.get("/admin/dashboard-data")
def admin_dashboard_data(
    request: Request,
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    verify_admin_secret(request)
    logger.info("Admin: dashboard-data days=%s", days)
    payload = get_admin_stats(db, days=days)
    payload["sources_health"] = get_sources_health()["sources"]
    return payload


@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request) -> HTMLResponse:
    verify_admin_secret(request)
    logger.info("Admin: dashboard HTML")
    return HTMLResponse(content=render_admin_dashboard_html())


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
    verify_admin_secret(request)
    webhook_url = body.webhook_url or build_webhook_url()
    logger.info("Admin: configurando webhook de Telegram")
    result = set_webhook(webhook_url)
    return {"ok": True, "webhook_url": webhook_url, "result": result}


@app.post("/admin/telegram/delete-webhook")
def admin_delete_webhook(request: Request) -> dict[str, Any]:
    verify_admin_secret(request)
    logger.info("Admin: eliminando webhook de Telegram")
    result = delete_webhook()
    return {"ok": True, "result": result}
