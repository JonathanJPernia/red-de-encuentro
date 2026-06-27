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
from app.services.query_validation import validate_search_query
from app.sources.base_external_source import BaseExternalSource, ExternalRecord
from app.sources.parsers.remix_data_parser import contains_contact_info, parse_remix_root_data

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0
MAX_RETRIES = 1
MIN_REQUEST_INTERVAL = 1.0

STATUS_MAP = {
    "missing": "missing",
    "found": "found",
    "shelter": "shelter",
    "refuge": "shelter",
    "refugio": "shelter",
    "hospital": "hospital",
    "hospitalized": "hospital",
    "hospitalizado": "hospital",
}

BLOCKED_RAW_FIELDS = frozenset(
    {
        "reporter",
        "phone",
        "email",
        "photourl",
        "photo_url",
        "idnumber",
        "id_number",
        "description",
        "foundnote",
        "found_note",
        "lastseen",
        "last_seen",
    }
)


class VenezuelaTeBuscaSource(BaseExternalSource):
    """
    Búsqueda acotada en Venezuela Te Busca vía endpoint interno del frontend.

    GET /_root.data?query=<query>
    Sin paginación automática ni bypass de Turnstile.
    """

    source_name = "Venezuela Te Busca"
    source_page_url = "https://venezuelatebusca.com"
    _last_request_at: float = 0.0

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.venezuela_te_busca_base_url.rstrip("/")
        self.timeout = DEFAULT_TIMEOUT

    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(settings.enable_venezuela_te_busca and settings.venezuela_te_busca_base_url)

    def search(self, query: str) -> list[PersonMatch]:
        validate_search_query(query)
        raw_text = self._fetch_root_data(query.strip())
        try:
            persons = parse_remix_root_data(raw_text)
        except Exception:
            logger.exception("Venezuela Te Busca: parser falló")
            return []

        matches: list[PersonMatch] = []
        for person in persons:
            try:
                record = _map_person(person, query, self.base_url)
                matches.append(_to_person_match(record))
            except Exception:
                logger.exception(
                    "Venezuela Te Busca: fila inválida id=%s",
                    person.get("id"),
                )
        return matches

    def _fetch_root_data(self, query: str) -> str:
        params = {"query": query}
        return self._get_text("/_root.data", params=params)

    def _get_text(self, path: str, *, params: dict[str, Any] | None = None) -> str:
        url = f"{self.base_url}{path}"
        headers = {
            "Accept": "*/*",
            "User-Agent": "BotTL/0.1 (+local search; missing-persons bot)",
            "Referer": f"{self.base_url}/?query={quote(params.get('query', '') if params else '')}",
        }
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            self._rate_limit()
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    return response.text
            except Exception as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "Reintento Venezuela Te Busca GET %s (intento %s): %s",
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
        elapsed = now - VenezuelaTeBuscaSource._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        VenezuelaTeBuscaSource._last_request_at = time.monotonic()


def _map_person(person: dict[str, Any], query: str, base_url: str) -> ExternalRecord:
    first = str(person.get("firstName") or "").strip()
    last = str(person.get("lastName") or "").strip()
    full_name = " ".join(part for part in [first, last] if part).strip()
    if not full_name:
        raise ValueError("Nombre vacío")

    document_id = _normalize_id_number(person.get("idNumber"))
    status = _map_status(person.get("status"), person.get("hospitalStatus"))
    source_url = f"{base_url}/?query={quote(query.strip())}"

    published_at = (
        _parse_datetime(person.get("lastActivityAt"))
        or _parse_datetime(person.get("updatedAt"))
        or _parse_datetime(person.get("createdAt"))
    )
    confidence = _score_match(full_name, document_id, query)
    raw_data = _build_safe_raw_data(person)

    return ExternalRecord(
        full_name=full_name,
        document_id=document_id,
        status=status,
        source_name=VenezuelaTeBuscaSource.source_name,
        source_url=source_url,
        published_at=published_at,
        raw_data=raw_data,
        confidence_score=confidence,
    )


def _normalize_id_number(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    digits = normalize_document_id(text)
    return digits if len(digits) >= 4 else None


def _map_status(raw_status: Any, hospital_status: Any = None) -> str:
    if raw_status is not None:
        key = str(raw_status).strip().lower()
        mapped = STATUS_MAP.get(key)
        if mapped:
            return mapped

    if hospital_status is not None:
        key = str(hospital_status).strip().lower()
        mapped = STATUS_MAP.get(key)
        if mapped == "hospital":
            return "hospital"

    return "unknown"


def _build_safe_raw_data(person: dict[str, Any]) -> dict | None:
    safe: dict[str, Any] = {}
    allowed = {
        "id": person.get("id"),
        "gender": person.get("gender"),
        "age": person.get("age"),
        "hospitalName": person.get("hospitalName"),
    }

    for key, value in allowed.items():
        if value is None or value == "":
            continue
        normalized_key = key.lower()
        if normalized_key in BLOCKED_RAW_FIELDS:
            continue
        if isinstance(value, str) and contains_contact_info(value):
            continue
        safe[key] = value

    return sanitize_raw_data(safe) if safe else None


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


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
