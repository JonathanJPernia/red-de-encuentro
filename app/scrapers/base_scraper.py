import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Appearance, Person, Source
from app.services.normalize_service import (
    document_id_last4,
    hash_document_id,
    normalize_name,
    normalize_status,
    sanitize_raw_data,
)

logger = logging.getLogger(__name__)


@dataclass
class ScrapedPerson:
    full_name: str
    document_id: str | None = None
    status: str = "missing"
    source_url: str | None = None
    published_at: datetime | None = None
    raw_data: dict | None = None


class BaseScraper(ABC):
    """Interfaz base para scrapers de fuentes públicas de desaparecidos."""

    source_name: str
    source_url: str
    reliability_level: int = 1

    @abstractmethod
    def fetch(self) -> str:
        """Descarga el contenido crudo de la fuente."""
        raise NotImplementedError

    @abstractmethod
    def parse(self, raw_content: str) -> list[ScrapedPerson]:
        """Parsea el contenido crudo en registros de personas."""
        raise NotImplementedError

    def run(self) -> int:
        """Descarga, parsea, normaliza y persiste registros en PostgreSQL."""
        raw_content = self.fetch()
        records = self.parse(raw_content)

        db = SessionLocal()
        try:
            source = self._get_or_create_source(db)
            saved = 0
            failed = 0
            for record in records:
                try:
                    self._upsert_person_and_appearance(db, source, record)
                    saved += 1
                except Exception:
                    failed += 1
                    logger.exception(
                        "Scraper %s: error en fila '%s'",
                        self.source_name,
                        record.full_name,
                    )
            db.commit()
            logger.info(
                "Scraper %s: %s registros procesados, %s fallidos",
                self.source_name,
                saved,
                failed,
            )
            return saved
        except Exception:
            logger.exception("Scraper %s falló durante la persistencia", self.source_name)
            db.rollback()
            raise
        finally:
            db.close()

    def _get_or_create_source(self, db: Session) -> Source:
        source = db.scalar(select(Source).where(Source.name == self.source_name))
        if source:
            source.url = self.source_url
            source.reliability_level = self.reliability_level
            return source

        source = Source(
            name=self.source_name,
            url=self.source_url,
            reliability_level=self.reliability_level,
        )
        db.add(source)
        db.flush()
        return source

    def _find_person(self, db: Session, record: ScrapedPerson, source: Source) -> Person | None:
        if record.document_id:
            doc_hash = hash_document_id(record.document_id)
            person = db.scalar(select(Person).where(Person.document_id_hash == doc_hash))
            if person:
                return person

        normalized = normalize_name(record.full_name)
        return db.scalar(
            select(Person)
            .join(Appearance)
            .where(
                Person.normalized_name == normalized,
                Appearance.source_id == source.id,
            )
        )

    def _upsert_person_and_appearance(
        self,
        db: Session,
        source: Source,
        record: ScrapedPerson,
    ) -> None:
        person = self._find_person(db, record, source)
        normalized = normalize_name(record.full_name)
        doc_hash = hash_document_id(record.document_id) if record.document_id else None
        last4 = document_id_last4(record.document_id) if record.document_id else None
        safe_raw_data = sanitize_raw_data(record.raw_data)
        resolved_source_url = record.source_url or self.source_url
        normalized_status = normalize_status(record.status)
        now = datetime.now(timezone.utc)

        if person:
            person.full_name = record.full_name
            person.normalized_name = normalized
            if doc_hash:
                person.document_id_hash = doc_hash
                person.document_id_last4 = last4
            person.updated_at = now
        else:
            person = Person(
                full_name=record.full_name,
                normalized_name=normalized,
                document_id_hash=doc_hash,
                document_id_last4=last4,
            )
            db.add(person)
            db.flush()

        appearance = db.scalar(
            select(Appearance).where(
                Appearance.person_id == person.id,
                Appearance.source_id == source.id,
                Appearance.source_url == resolved_source_url,
            )
        )

        if appearance:
            appearance.status = normalized_status
            appearance.raw_data = safe_raw_data
            appearance.source_url = resolved_source_url
            appearance.published_at = record.published_at
        else:
            db.add(
                Appearance(
                    person_id=person.id,
                    source_id=source.id,
                    status=normalized_status,
                    raw_data=safe_raw_data,
                    source_url=resolved_source_url,
                    published_at=record.published_at,
                )
            )
