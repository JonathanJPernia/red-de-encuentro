from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import quote

from app.config import get_settings
from app.schemas.search import PersonMatch, SourceMatch
from app.services.normalize_service import (
    document_id_last4,
    hash_document_id,
    is_document_query,
    normalize_document_id,
    normalize_name,
    sanitize_raw_data,
    split_name_and_document,
)
from app.sources.base_external_source import BaseExternalSource, ExternalRecord
from app.sources.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

SOURCE_PAGE_URL = "https://emergencia.joch.dev/"
TABLE_PATH = "/rest/v1/reportes_emergencias"

STATUS_MAP = {
    "desaparecido": "missing",
    "desaparecida": "missing",
    "a salvo": "found",
    "salvo": "found",
    "encontrado": "found",
    "hospital": "hospital",
    "refugio": "shelter",
    "albergue": "shelter",
    "atrapado / herido": "hospital",
}


class EmergenciaJochSource(BaseExternalSource):
    """
    Búsqueda acotada vía filtros PostgREST (ilike), equivalente al buscador público.
    No realiza dump masivo de la tabla.
    """

    source_name = "Emergencia Joch.dev"
    source_page_url = SOURCE_PAGE_URL

    def __init__(self) -> None:
        settings = get_settings()
        self.client = SupabaseClient(
            base_url=settings.emergencia_joch_supabase_url,
            anon_key=settings.emergencia_joch_supabase_anon_key,
        )

    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(
            settings.emergencia_joch_supabase_url and settings.emergencia_joch_supabase_anon_key
        )

    def search(self, query: str) -> list[PersonMatch]:
        params = _build_search_params(query)
        rows = self.client.get(TABLE_PATH, params=params)
        if not isinstance(rows, list):
            logger.warning("Emergencia Joch.dev: respuesta inesperada tipo %s", type(rows))
            return []

        matches: list[PersonMatch] = []
        for row in rows:
            try:
                record = _map_row(row, query)
                matches.append(_to_person_match(record))
            except Exception:
                logger.exception(
                    "Emergencia Joch.dev: fila inválida id=%s",
                    row.get("id"),
                )
        return matches


def _build_search_params(query: str) -> dict[str, str]:
    select = "id,nombre_completo,estado_persona,detalles_emergencia,created_at"
    if is_document_query(query):
        digits = normalize_document_id(query)
        return {
            "select": select,
            "nombre_completo": f"ilike.*{digits}*",
            "limit": "10",
            "order": "created_at.desc",
        }

    term = quote(query.strip(), safe="")
    return {
        "select": select,
        "or": f"(nombre_completo.ilike.*{term}*,detalles_emergencia.ilike.*{term}*)",
        "limit": "10",
        "order": "created_at.desc",
    }


def _map_row(row: dict, query: str) -> ExternalRecord:
    raw_name = (row.get("nombre_completo") or "").strip()
    if not raw_name:
        raise ValueError("Nombre vacío")

    full_name, document_id = split_name_and_document(raw_name)
    if not document_id:
        document_id = split_name_and_document(row.get("detalles_emergencia") or "")[1]

    status_key = (row.get("estado_persona") or "unknown").strip().lower()
    status = STATUS_MAP.get(status_key, "unknown")
    report_id = row.get("id")
    source_url = f"{SOURCE_PAGE_URL}#reporte-{report_id}"
    published_at = _parse_datetime(row.get("created_at"))
    confidence = _score_match(full_name, document_id, query)

    raw_data = sanitize_raw_data(
        {
            "report_id": report_id,
            "estado_persona": row.get("estado_persona"),
            "detalles_emergencia": row.get("detalles_emergencia"),
        }
    )

    return ExternalRecord(
        full_name=full_name,
        document_id=document_id,
        status=status,
        source_name=EmergenciaJochSource.source_name,
        source_url=source_url,
        published_at=published_at,
        raw_data=raw_data,
        confidence_score=confidence,
    )


def _score_match(full_name: str, document_id: str | None, query: str) -> float:
    if is_document_query(query) and document_id:
        if normalize_document_id(query) == normalize_document_id(document_id):
            return 100.0

    normalized_query = normalize_name(query)
    normalized_name = normalize_name(full_name)
    if normalized_query == normalized_name:
        return 95.0
    if normalized_query in normalized_name:
        return 80.0
    return 80.0


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
