from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.schemas.search import PersonMatch
from app.sources.http_debug import detect_block_reason
from app.sources.source_health_manager import get_status, record_failure, record_success, should_skip

logger = logging.getLogger(__name__)


@dataclass
class ExternalRecord:
    """Registro normalizado desde una fuente externa antes de mapear a PersonMatch."""

    full_name: str
    document_id: str | None = None
    status: str = "unknown"
    source_name: str = ""
    source_url: str = ""
    published_at: datetime | None = None
    raw_data: dict | None = None
    confidence_score: float = 80.0


@dataclass
class ProviderSearchStats:
    raw_count: int = 0
    mapped_count: int = 0
    error: str | None = None
    skipped: bool = False
    reason: str | None = None
    degraded_until: datetime | None = None
    provider_status: str = "ok"


class BaseExternalSource(ABC):
    """Proveedor de búsqueda externa (no volcado masivo de datos)."""

    source_name: str
    source_page_url: str

    def __init__(self) -> None:
        self.last_search_stats = ProviderSearchStats()

    def _ensure_search_stats(self) -> None:
        if not hasattr(self, "last_search_stats"):
            self.last_search_stats = ProviderSearchStats()

    @abstractmethod
    def is_configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str) -> list[PersonMatch]:
        raise NotImplementedError

    def safe_search(self, query: str) -> list[PersonMatch]:
        self.last_search_stats = ProviderSearchStats()
        if not self.is_configured():
            logger.info("Fuente externa omitida (sin configurar): %s", self.source_name)
            self.last_search_stats.provider_status = "skipped"
            return []

        if should_skip(self.source_name):
            health = get_status(self.source_name)
            self.last_search_stats.skipped = True
            self.last_search_stats.provider_status = "degraded"
            self.last_search_stats.reason = health.get("reason")
            self.last_search_stats.degraded_until = health.get("degraded_until")
            self.last_search_stats.error = health.get("reason")
            return []

        try:
            matches = self.search(query)
            stats = self.last_search_stats
            if stats.mapped_count == 0:
                stats.mapped_count = len(matches)
            if stats.raw_count == 0:
                stats.raw_count = stats.mapped_count
            record_success(self.source_name)
            stats.provider_status = "ok"
            return matches
        except Exception as exc:
            reason = detect_block_reason(exc=exc)
            record_failure(self.source_name, str(exc), reason=reason)
            logger.exception("Fuente externa falló: %s", self.source_name)
            health = get_status(self.source_name)
            self.last_search_stats.error = str(exc)
            self.last_search_stats.reason = health.get("reason")
            self.last_search_stats.degraded_until = health.get("degraded_until")
            self.last_search_stats.provider_status = "error"
            return []
