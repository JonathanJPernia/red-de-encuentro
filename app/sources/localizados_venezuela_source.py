from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.config import get_settings
from app.schemas.search import PersonMatch, SourceMatch
from app.services.query_scoring import score_query_match
from app.services.normalize_service import (
    document_id_last4,
    extract_document_from_text,
    hash_document_id,
    is_document_query,
    normalize_document_id,
    normalize_name,
    sanitize_raw_data,
)
from app.services.query_validation import validate_search_query
from app.sources.base_external_source import BaseExternalSource, ExternalRecord
from app.sources.http_debug import raise_for_status_logged

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0
MAX_RETRIES = 1
MIN_REQUEST_INTERVAL = 1.0
SEARCH_LIMIT = 10
STATUS_FOUND = "found"


class LocalizadosVenezuelaSource(BaseExternalSource):
    """
    Búsqueda acotada en la API pública de Localizados Venezuela.

    Registra personas ya localizadas (no desaparecidas).
    GET /api/v1/localizados?q=<query>&page=1&limit=10
    """

    source_name = "Localizados Venezuela"
    source_page_url = "https://localizadosvenezuela.com"
    _last_request_at: float = 0.0

    def __init__(self) -> None:
        super().__init__()
        settings = get_settings()
        self.base_url = settings.localizados_venezuela_base_url.rstrip("/")
        self.timeout = DEFAULT_TIMEOUT

    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(
            settings.enable_localizados_venezuela and settings.localizados_venezuela_base_url
        )

    def search(self, query: str) -> list[PersonMatch]:
        validate_search_query(query)
        payload = self._fetch_search(query.strip())
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            logger.warning("Localizados Venezuela: respuesta inesperada")
            return []

        self._ensure_search_stats()
        self.last_search_stats.raw_count = len(rows)

        matches: list[PersonMatch] = []
        for row in rows:
            try:
                record = _map_row(row, query, self.base_url)
                matches.append(_to_person_match(record))
            except Exception:
                logger.exception(
                    "Localizados Venezuela: fila inválida slug=%s",
                    row.get("slug"),
                )
        self.last_search_stats.mapped_count = len(matches)
        return matches

    def _fetch_search(self, query: str) -> dict[str, Any]:
        path = "/api/v1/localizados"
        params = {"q": query, "page": 1, "limit": SEARCH_LIMIT}
        return self._get_json(path, params=params)

    def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {
            "Accept": "application/json",
            "User-Agent": "BotTL/0.1 (+local search; missing-persons bot)",
        }
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            self._rate_limit()
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=headers, params=params)
                    raise_for_status_logged(self.source_name, response)
                    data = response.json()
                    if not isinstance(data, dict):
                        raise ValueError("Respuesta JSON inválida")
                    return data
            except Exception as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "Reintento Localizados Venezuela GET %s (intento %s): %s",
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
        elapsed = now - LocalizadosVenezuelaSource._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        LocalizadosVenezuelaSource._last_request_at = time.monotonic()


def _map_row(row: dict, query: str, base_url: str) -> ExternalRecord:
    full_name = (row.get("nombreCompleto") or "").strip()
    if not full_name:
        raise ValueError("Nombre vacío")

    observaciones = row.get("observaciones") or ""
    document_id = extract_document_from_text(f"{full_name} {observaciones}")

    slug = row.get("slug")
    if slug:
        source_url = f"{base_url}/localizados/{slug}"
    else:
        source_url = f"{base_url}/buscar?q={quote(query.strip())}"

    published_at = _parse_datetime(row.get("publicadoEn"))
    confidence = _score_match(full_name, document_id, query)

    raw_data = sanitize_raw_data(
        {
            "slug": slug,
            "condicion": row.get("condicion"),
            "lugar_nombre": row.get("lugarNombre"),
            "fuente_tipo": (row.get("fuente") or {}).get("tipo"),
            "fuente_nombre": (row.get("fuente") or {}).get("nombre"),
            "fuente_fecha": (row.get("fuente") or {}).get("fecha"),
        }
    )

    return ExternalRecord(
        full_name=full_name,
        document_id=document_id,
        status=STATUS_FOUND,
        source_name=LocalizadosVenezuelaSource.source_name,
        source_url=source_url,
        published_at=published_at,
        raw_data=raw_data,
        confidence_score=confidence,
    )


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


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
