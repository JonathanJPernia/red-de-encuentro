import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import Appearance, Person
from app.schemas.search import PersonMatch, SearchResponse, SourceMatch
from app.services.match_consolidation import consolidate_matches, rank_matches
from app.services.normalize_service import (
    hash_document_id,
    is_document_query,
    normalize_document_id,
    normalize_name,
)
from app.services.privacy_log import mask_query_for_log
from app.services.query_validation import validate_search_query
from app.sources.registry import get_external_sources
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)

MAX_RESULTS = 10
BOT_MAX_RESULTS = 5
SCORE_EXACT_DOCUMENT = 100.0
SCORE_EXACT_NAME = 95.0
SCORE_PARTIAL_NAME = 80.0
FUZZY_MIN_SCORE = 80.0
FUZZY_SCORE_THRESHOLD = 90.0


class SearchService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def search(self, query: str, limit: int = MAX_RESULTS) -> SearchResponse:
        stripped = query.strip()
        if not stripped:
            return SearchResponse(query=query, matches=[])

        validate_search_query(stripped)
        logger.info("Búsqueda q=%s", mask_query_for_log(stripped))

        if is_document_query(stripped):
            matches = self._search_local_by_document(stripped, limit=limit)
            response_query = f"***{normalize_document_id(stripped)[-4:]}"
        else:
            matches = self._search_local_by_name(stripped, limit=limit)
            response_query = stripped

        if self.settings.enable_external_sources:
            external_matches = self._search_external_providers(stripped)
            matches = matches + external_matches

        matches = consolidate_matches(matches)
        matches = rank_matches(matches, stripped)

        return SearchResponse(query=response_query, matches=matches[:limit])

    def _search_external_providers(self, query: str) -> list[PersonMatch]:
        results: list[PersonMatch] = []
        for provider in get_external_sources():
            provider_matches = provider.safe_search(query)
            logger.info(
                "Fuente externa %s: %s resultados para q=%s",
                provider.source_name,
                len(provider_matches),
                mask_query_for_log(query),
            )
            results.extend(provider_matches)
        return results

    def _person_query(self):
        return select(Person).options(
            selectinload(Person.appearances).selectinload(Appearance.source)
        )

    def _to_person_match(self, person: Person, confidence_score: float) -> PersonMatch:
        sources = [
            SourceMatch(
                name=appearance.source.name,
                status=appearance.status,
                source_url=appearance.source_url,
                published_at=appearance.published_at,
            )
            for appearance in person.appearances
        ]
        return PersonMatch(
            full_name=person.full_name,
            document_id_last4=person.document_id_last4,
            document_id_hash=person.document_id_hash,
            confidence_score=round(confidence_score, 2),
            sources=sources,
        )

    def _search_local_by_document(self, document_id: str, limit: int) -> list[PersonMatch]:
        doc_hash = hash_document_id(document_id)
        persons = self.db.scalars(
            self._person_query().where(Person.document_id_hash == doc_hash).limit(limit)
        ).all()
        return [self._to_person_match(person, SCORE_EXACT_DOCUMENT) for person in persons]

    def _search_local_by_name(self, name: str, limit: int) -> list[PersonMatch]:
        normalized_query = normalize_name(name)
        if not normalized_query:
            return []

        persons = self.db.scalars(self._person_query()).all()
        if not persons:
            return []

        ranked: dict[int, float] = {}

        for person in persons:
            if person.normalized_name == normalized_query:
                ranked[person.id] = max(ranked.get(person.id, 0), SCORE_EXACT_NAME)
            elif normalized_query in person.normalized_name:
                ranked[person.id] = max(ranked.get(person.id, 0), SCORE_PARTIAL_NAME)

        choices = {person.id: person.normalized_name for person in persons}
        fuzzy_matches = process.extract(
            normalized_query,
            choices,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=FUZZY_SCORE_THRESHOLD,
            limit=limit * 2,
        )
        for _, score, person_id in fuzzy_matches:
            if score >= FUZZY_SCORE_THRESHOLD:
                ranked[person_id] = max(ranked.get(person_id, 0), float(score))

        ranked = {
            person_id: score
            for person_id, score in ranked.items()
            if score >= FUZZY_MIN_SCORE
        }

        if not ranked:
            return []

        person_map = {person.id: person for person in persons}
        sorted_ids = sorted(ranked, key=lambda pid: ranked[pid], reverse=True)[:limit]

        return [
            self._to_person_match(person_map[pid], ranked[pid])
            for pid in sorted_ids
            if pid in person_map
        ]
