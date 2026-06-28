import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import Appearance, Person
from app.schemas.search import PersonMatch, ProviderDebugInfo, SearchDebugInfo, SearchResponse, SourceMatch
from app.services.match_consolidation import consolidate_matches, rank_matches
from app.services.name_matching import (
    BROAD_QUERY_MESSAGE,
    is_broad_single_word_query,
    is_single_token_query,
    min_score_for_query,
    score_name_match,
    tokenize,
)
from app.services.normalize_service import (
    hash_document_id,
    is_document_query,
    normalize_document_id,
)
from app.services.privacy_log import mask_query_for_log
from app.services.query_validation import validate_search_query
from app.sources.base_external_source import BaseExternalSource
from app.sources.registry import OPTIONAL_SOURCE_FLAGS

logger = logging.getLogger(__name__)

MAX_RESULTS = 10
BOT_MAX_RESULTS = 5
SCORE_EXACT_DOCUMENT = 100.0
MIN_RELEVANT_SCORE = 80.0


@dataclass
class _ProviderRunResult:
    matches: list[PersonMatch]
    info: ProviderDebugInfo


@dataclass
class _ExternalSearchOutcome:
    matches: list[PersonMatch]
    providers: list[ProviderDebugInfo]


class SearchService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def search(
        self,
        query: str,
        limit: int = MAX_RESULTS,
        *,
        include_debug: bool = False,
    ) -> SearchResponse:
        stripped = query.strip()
        if not stripped:
            return SearchResponse(query=query, matches=[])

        validate_search_query(stripped)
        logger.info("Búsqueda q=%s", mask_query_for_log(stripped))

        debug_info: SearchDebugInfo | None = None

        if is_document_query(stripped):
            matches = self._search_local_by_document(stripped, limit=limit)
            response_query = f"***{normalize_document_id(stripped)[-4:]}"
        else:
            if is_broad_single_word_query(stripped):
                raise ValueError(BROAD_QUERY_MESSAGE)

            matches = self._search_local_by_name(stripped, limit=limit)
            response_query = stripped

        if self.settings.enable_external_sources and not is_broad_single_word_query(stripped):
            outcome = self._search_external_providers(stripped)
            if include_debug:
                debug_info = SearchDebugInfo(providers=outcome.providers)

            if is_document_query(stripped):
                matches = matches + outcome.matches
            else:
                matches = matches + outcome.matches

        matches = self._apply_name_filters(stripped, matches)
        matches = consolidate_matches(matches)
        matches = rank_matches(matches, stripped)

        return SearchResponse(
            query=response_query,
            matches=matches[:limit],
            debug=debug_info,
        )

    def _apply_name_filters(self, query: str, matches: list[PersonMatch]) -> list[PersonMatch]:
        if is_document_query(query):
            return matches

        threshold = min_score_for_query(query)
        filtered = [match for match in matches if match.confidence_score >= threshold]

        if is_single_token_query(query):
            return filtered

        if len(tokenize(query)) >= 2:
            if filtered and max(match.confidence_score for match in filtered) < MIN_RELEVANT_SCORE:
                raise ValueError(BROAD_QUERY_MESSAGE)

        return filtered

    def _score_and_filter_match(self, query: str, match: PersonMatch) -> PersonMatch | None:
        score = score_name_match(query, match.full_name)
        if score is None:
            return None
        return match.model_copy(update={"confidence_score": round(score, 2)})

    def _filter_name_matches(self, query: str, matches: list[PersonMatch]) -> list[PersonMatch]:
        filtered: list[PersonMatch] = []
        for match in matches:
            scored = self._score_and_filter_match(query, match)
            if scored is not None:
                filtered.append(scored)
        return filtered

    def _search_external_providers(self, query: str) -> _ExternalSearchOutcome:
        if is_broad_single_word_query(query):
            return _ExternalSearchOutcome(matches=[], providers=[])

        results: list[PersonMatch] = []
        providers: list[ProviderDebugInfo] = []

        for provider in self._all_external_providers():
            provider_result = self._run_external_provider(provider, query)
            providers.append(provider_result.info)
            results.extend(provider_result.matches)

        return _ExternalSearchOutcome(matches=results, providers=providers)

    def _all_external_providers(self) -> list[BaseExternalSource]:
        return [source_cls() for source_cls in OPTIONAL_SOURCE_FLAGS]

    def _run_external_provider(
        self,
        provider: BaseExternalSource,
        query: str,
    ) -> _ProviderRunResult:
        enabled = provider.is_configured()
        if not enabled:
            return _ProviderRunResult(
                matches=[],
                info=ProviderDebugInfo(
                    name=provider.source_name,
                    enabled=False,
                    status="skipped",
                    raw_count=0,
                    mapped_count=0,
                    filtered_count=0,
                    error=None,
                ),
            )

        provider_matches = provider.safe_search(query)
        stats = provider.last_search_stats
        filtered = self._filter_name_matches(query, provider_matches)

        logger.info(
            "Fuente externa %s: raw=%s mapped=%s filtered=%s q=%s",
            provider.source_name,
            stats.raw_count,
            stats.mapped_count,
            len(filtered),
            mask_query_for_log(query),
        )

        status = "error" if stats.error else "ok"
        return _ProviderRunResult(
            matches=filtered,
            info=ProviderDebugInfo(
                name=provider.source_name,
                enabled=True,
                status=status,
                raw_count=stats.raw_count,
                mapped_count=stats.mapped_count,
                filtered_count=len(filtered),
                error=stats.error,
            ),
        )

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
        persons = self.db.scalars(self._person_query()).all()
        if not persons:
            return []

        ranked: dict[int, float] = {}
        for person in persons:
            score = score_name_match(name, person.full_name)
            if score is None:
                continue
            ranked[person.id] = max(ranked.get(person.id, 0), score)

        if not ranked:
            return []

        person_map = {person.id: person for person in persons}
        sorted_ids = sorted(ranked, key=lambda pid: ranked[pid], reverse=True)[:limit]

        return [
            self._to_person_match(person_map[pid], ranked[pid])
            for pid in sorted_ids
            if pid in person_map
        ]
