from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.schemas.search import PersonMatch

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


class BaseExternalSource(ABC):
    """Proveedor de búsqueda externa (no volcado masivo de datos)."""

    source_name: str
    source_page_url: str

    @abstractmethod
    def is_configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str) -> list[PersonMatch]:
        raise NotImplementedError

    def safe_search(self, query: str) -> list[PersonMatch]:
        if not self.is_configured():
            logger.info("Fuente externa omitida (sin configurar): %s", self.source_name)
            return []
        try:
            return self.search(query)
        except Exception:
            logger.exception("Fuente externa falló: %s", self.source_name)
            return []
