from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.config import get_settings
from app.schemas.search import PersonMatch, SourceMatch
from app.services.normalize_service import (
    document_id_last4,
    hash_document_id,
    is_document_query,
    normalize_document_id,
    normalize_name,
    sanitize_raw_data,
)
from app.services.query_scoring import score_query_match
from app.services.query_validation import validate_search_query
from app.sources.base_external_source import BaseExternalSource, ExternalRecord

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0
MAX_RETRIES = 1
MIN_REQUEST_INTERVAL = 1.0
SEARCH_PAGE = 1
SEARCH_PAGE_SIZE = 10

STATUS_MAP = {
    "localizado": "found",
    "sin-contacto": "missing",
    "sin_contacto": "missing",
}

BLOCKED_RAW_FIELDS = frozenset(
    {
        "telefonocontacto",
        "telefono_contacto",
        "contacto",
        "nombrecontacto",
        "nombre_contacto",
        "correocontacto",
        "correo_contacto",
        "localizadocontacto",
        "localizado_contacto",
        "localizadopor",
        "localizado_por",
        "localizadorelacion",
        "localizado_relacion",
        "localizadonota",
        "localizado_nota",
        "direccion",
        "direccion_exacta",
        "foto",
        "foto_url",
        "fechanacimiento",
        "fecha_nacimiento",
        "cedula",
        "document_id",
        "documento",
    }
)


class DesaparecidosTerremotoVenezuelaSource(BaseExternalSource):
    """
    Búsqueda acotada en la API pública de Desaparecidos Terremoto Venezuela.

    GET /api/personas?page=1&pageSize=10&q=<query>
    Solo primera página; sin dump masivo.
    """

    source_name = "Desaparecidos Terremoto Venezuela"
    source_page_url = "https://desaparecidosterremotovenezuela.com"
    _last_request_at: float = 0.0

    def __init__(self) -> None:
        super().__init__()
        settings = get_settings()
        self.api_base_url = settings.desaparecidos_terremoto_base_url.rstrip("/")
        self.public_base_url = settings.desaparecidos_terremoto_public_url.rstrip("/")
        self.timeout = DEFAULT_TIMEOUT

    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(
            settings.enable_desaparecidos_terremoto_venezuela
            and settings.desaparecidos_terremoto_base_url
            and settings.desaparecidos_terremoto_public_url
        )

    def search(self, query: str) -> list[PersonMatch]:
        validate_search_query(query)
        payload = self._fetch_search(query.strip())
        items = payload.get("items") or payload.get("data") or []
        if not isinstance(items, list):
            logger.warning("Desaparecidos Terremoto Venezuela: respuesta inesperada")
            return []

        matches: list[PersonMatch] = []
        for item in items:
            try:
                record = _map_item(item, query, self.public_base_url)
                matches.append(_to_person_match(record))
            except Exception:
                logger.exception(
                    "Desaparecidos Terremoto Venezuela: fila inválida id=%s",
                    item.get("id"),
                )
        return matches

    def _fetch_search(self, query: str) -> dict[str, Any]:
        params = {
            "page": SEARCH_PAGE,
            "pageSize": SEARCH_PAGE_SIZE,
            "q": query,
        }
        return self._get_json("/api/personas", params=params)

    def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.api_base_url}{path}"
        headers = {
            "Accept": "application/json",
            "User-Agent": "BotTL/0.1 (+local search; missing-persons bot)",
            "Origin": self.public_base_url,
            "Referer": f"{self.public_base_url}/",
        }
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            self._rate_limit()
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict):
                        raise ValueError("Respuesta JSON inválida")
                    return data
            except Exception as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "Reintento Desaparecidos Terremoto GET %s (intento %s): %s",
                        path,
                        attempt + 1,
                        exc,
                    )
                    continue
                break

        assert last_error is not None
        raise last_error

    def _rate_limit(self) -> None:
        now = time.monotonic()
        elapsed = now - DesaparecidosTerremotoVenezuelaSource._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        DesaparecidosTerremotoVenezuelaSource._last_request_at = time.monotonic()


def _map_item(item: dict, query: str, public_base_url: str) -> ExternalRecord:
    full_name = (item.get("nombre") or "").strip()
    if not full_name:
        raise ValueError("Nombre vacío")

    document_id = _normalize_cedula(item.get("cedula"))
    status = _map_status(item.get("estado") or item.get("status"))
    person_id = item.get("id")

    if person_id is not None:
        source_url = f"{public_base_url}/personas/{person_id}"
    else:
        source_url = f"{public_base_url}/?q={quote(query.strip())}"

    published_at = _parse_datetime(item.get("fecha")) or _parse_datetime(item.get("createdAt"))
    confidence = _score_match(full_name, document_id, query)
    raw_data = _build_safe_raw_data(item)

    return ExternalRecord(
        full_name=full_name,
        document_id=document_id,
        status=status,
        source_name=DesaparecidosTerremotoVenezuelaSource.source_name,
        source_url=source_url,
        published_at=published_at,
        raw_data=raw_data,
        confidence_score=confidence,
    )


def _normalize_cedula(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    digits = normalize_document_id(text)
    return digits if len(digits) >= 4 else None


def _map_status(raw_status: Any) -> str:
    if raw_status is None:
        return "unknown"
    key = str(raw_status).strip().lower().replace("_", "-")
    return STATUS_MAP.get(key, "unknown")


def _build_safe_raw_data(item: dict) -> dict | None:
    safe: dict[str, Any] = {}
    for key, value in item.items():
        normalized_key = key.strip().lower().replace(" ", "_")
        if normalized_key in BLOCKED_RAW_FIELDS:
            continue
        if normalized_key in {"estado", "municipio", "parroquia", "id", "estado_id", "municipio_id"}:
            safe[key] = value

    return sanitize_raw_data(safe) if safe else None


def _score_match(full_name: str, document_id: str | None, query: str) -> float:
    return score_query_match(query, full_name, document_id)


def _to_person_match(record: ExternalRecord) -> PersonMatch:
    last4 = None
    doc_hash = None
    if record.document_id:
        try:
            last4 = document_id_last4(record.document_id)
            doc_hash = hash_document_id(record.document_id)
        except ValueError:
            last4 = None
            doc_hash = None

    return PersonMatch(
        full_name=record.full_name,
        document_id_last4=last4,
        document_id_hash=doc_hash,
        confidence_score=record.confidence_score,
        sources=[
            SourceMatch(
                name=record.source_name,
                status=record.status,
                source_url=record.source_url,
                published_at=record.published_at,
            )
        ],
    )


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
