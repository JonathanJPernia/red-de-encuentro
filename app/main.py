import logging

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

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

app = FastAPI(
    title="Bot TL - Desaparecidos",
    description="Backend para búsqueda de personas en listas públicas de desaparecidos",
    version="0.1.0",
    debug=settings.debug,
)


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
