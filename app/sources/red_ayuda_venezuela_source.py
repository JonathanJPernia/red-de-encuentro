from __future__ import annotations

import logging
from datetime import datetime

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
    normalize_status,
    sanitize_raw_data,
)
from app.sources.base_external_source import BaseExternalSource, ExternalRecord
from app.sources.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

SOURCE_PAGE_URL = "https://redayudavenezuela.com/buscar"
RPC_PATH = "/rest/v1/rpc/search_people"

CATEGORY_STATUS = {
    "missing": "missing",
    "desaparecido": "missing",
    "hospital": "hospital",
    "salvo": "found",
    "found": "found",
    "shelter": "shelter",
}


def build_payload(query: str) -> dict[str, str]:
    """
    Body confirmado desde el frontend de Red Ayuda Venezuela.

    POST /rest/v1/rpc/search_people
    {"q": "<texto>"}

    Si el frontend cambia, ajustar solo esta función.
    """
    return {"q": query.strip()}


class RedAyudaVenezuelaSource(BaseExternalSource):
    source_name = "Red Ayuda Venezuela"
    source_page_url = SOURCE_PAGE_URL

    def __init__(self) -> None:
        super().__init__()
        settings = get_settings()
        self.client = SupabaseClient(
            base_url=settings.red_ayuda_supabase_url,
            anon_key=settings.red_ayuda_supabase_anon_key,
        )

    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(settings.red_ayuda_supabase_url and settings.red_ayuda_supabase_anon_key)

    def search(self, query: str) -> list[PersonMatch]:
        payload = build_payload(query)
        rows = self.client.post(RPC_PATH, json=payload)
        if not isinstance(rows, list):
            logger.warning("Red Ayuda Venezuela: respuesta inesperada tipo %s", type(rows))
            return []

        records = [_map_row(row, query) for row in rows]
        return [_to_person_match(record) for record in records]


def _map_row(row: dict, query: str) -> ExternalRecord:
    full_name = (row.get("name") or "").strip()
    if not full_name:
        raise ValueError("Nombre vacío")

    detail = row.get("detail") or ""
    document_id = extract_document_from_text(f"{full_name} {detail}")
    category = (row.get("category") or "unknown").lower()
    status = CATEGORY_STATUS.get(category, normalize_status(category))

    confidence = _score_match(full_name, document_id, query)
    slug = row.get("slug")
    source_url = f"{SOURCE_PAGE_URL}?q={slug}" if slug else SOURCE_PAGE_URL

    raw_data = sanitize_raw_data(
        {
            "category": row.get("category"),
            "label": row.get("label"),
            "detail": detail,
            "slug": slug,
        }
    )

    return ExternalRecord(
        full_name=full_name,
        document_id=document_id,
        status=status,
        source_name=RedAyudaVenezuelaSource.source_name,
        source_url=source_url,
        published_at=None,
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
