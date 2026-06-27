from __future__ import annotations

from datetime import datetime

from rapidfuzz import fuzz

from app.schemas.search import PersonMatch, SourceMatch
from app.services.normalize_service import (
    hash_document_id,
    is_document_query,
    normalize_document_id,
    normalize_name,
    normalize_status,
)

DEDUP_NAME_SIMILARITY = 94
DEDUP_REINFORCED_SIMILARITY = 90

STATUS_PRIORITY = {
    "found": 5,
    "hospital": 4,
    "shelter": 3,
    "missing": 2,
    "unknown": 1,
}


def name_similarity(left: str, right: str) -> float:
    return float(
        fuzz.token_sort_ratio(normalize_name(left), normalize_name(right))
    )


def consolidate_status(statuses: list[str]) -> tuple[str, bool]:
    normalized = [normalize_status(status) for status in statuses if status]
    if not normalized:
        return "unknown", False

    unique = set(normalized)
    consolidated = max(unique, key=lambda status: STATUS_PRIORITY.get(status, 0))
    return consolidated, len(unique) > 1


def latest_published_at(sources: list[SourceMatch]) -> datetime | None:
    dates = [source.published_at for source in sources if source.published_at is not None]
    return max(dates) if dates else None


def merge_sources(
    left: list[SourceMatch],
    right: list[SourceMatch],
) -> list[SourceMatch]:
    seen: set[tuple[str, str | None]] = set()
    merged: list[SourceMatch] = []
    for source in left + right:
        key = (source.name, source.source_url)
        if key in seen:
            continue
        seen.add(key)
        merged.append(source)
    return merged


def should_merge(left: PersonMatch, right: PersonMatch) -> bool:
    if left.document_id_hash and right.document_id_hash:
        if left.document_id_hash == right.document_id_hash:
            return True

    if left.document_id_last4 and right.document_id_last4:
        if (
            left.document_id_last4 == right.document_id_last4
            and name_similarity(left.full_name, right.full_name) >= DEDUP_NAME_SIMILARITY
        ):
            return True

    similarity = name_similarity(left.full_name, right.full_name)
    if similarity >= DEDUP_NAME_SIMILARITY:
        return True

    if similarity >= DEDUP_REINFORCED_SIMILARITY and _has_reinforcing_signal(left, right):
        return True

    return False


def _has_reinforcing_signal(left: PersonMatch, right: PersonMatch) -> bool:
    left_statuses = {normalize_status(source.status) for source in left.sources}
    right_statuses = {normalize_status(source.status) for source in right.sources}
    shared_statuses = (left_statuses & right_statuses) - {"unknown"}
    if shared_statuses:
        return True

    left_dates = {source.published_at.date() for source in left.sources if source.published_at}
    right_dates = {source.published_at.date() for source in right.sources if source.published_at}
    return bool(left_dates & right_dates)


def cluster_matches(matches: list[PersonMatch]) -> list[list[PersonMatch]]:
    if not matches:
        return []

    parent = list(range(len(matches)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_index in range(len(matches)):
        for right_index in range(left_index + 1, len(matches)):
            if should_merge(matches[left_index], matches[right_index]):
                union(left_index, right_index)

    groups: dict[int, list[PersonMatch]] = {}
    for index, match in enumerate(matches):
        root = find(index)
        groups.setdefault(root, []).append(match)

    return list(groups.values())


def consolidate_group(group: list[PersonMatch]) -> PersonMatch:
    if len(group) == 1:
        return finalize_match(group[0])

    best = max(group, key=lambda match: (match.confidence_score, len(match.full_name)))
    merged_sources = merge_sources(*(match.sources for match in group))
    all_statuses = [source.status for match in group for source in match.sources]
    status, status_conflict = consolidate_status(all_statuses)

    document_id_hash = next((match.document_id_hash for match in group if match.document_id_hash), None)
    document_id_last4 = next(
        (match.document_id_last4 for match in group if match.document_id_last4),
        None,
    )
    confidence_score = max(match.confidence_score for match in group)

    return PersonMatch(
        full_name=best.full_name,
        document_id_last4=document_id_last4,
        document_id_hash=document_id_hash,
        status=status,
        confidence_score=round(confidence_score, 2),
        sources=merged_sources,
        status_conflict=status_conflict,
        source_count=len(merged_sources),
        latest_published_at=latest_published_at(merged_sources),
    )


def finalize_match(match: PersonMatch) -> PersonMatch:
    statuses = [source.status for source in match.sources]
    status, status_conflict = consolidate_status(statuses) if statuses else (match.status, False)
    sources = merge_sources(match.sources, [])

    return PersonMatch(
        full_name=match.full_name,
        document_id_last4=match.document_id_last4,
        document_id_hash=match.document_id_hash,
        status=status or "unknown",
        confidence_score=match.confidence_score,
        sources=sources,
        status_conflict=status_conflict,
        source_count=len(sources),
        latest_published_at=latest_published_at(sources),
    )


def consolidate_matches(matches: list[PersonMatch]) -> list[PersonMatch]:
    return [consolidate_group(group) for group in cluster_matches(matches)]


def rank_matches(matches: list[PersonMatch], query: str) -> list[PersonMatch]:
    doc_query = is_document_query(query)
    normalized_query = normalize_name(query)

    def sort_key(match: PersonMatch) -> tuple:
        exact_doc = _is_exact_document_match(match, query) if doc_query else False
        exact_name = (
            not doc_query and normalize_name(match.full_name) == normalized_query
        )

        priority = 0
        if exact_doc:
            priority = 1000
        elif exact_name:
            priority = 900

        latest_ts = match.latest_published_at.timestamp() if match.latest_published_at else 0.0
        found_boost = 1 if match.status == "found" and (exact_doc or exact_name) else 0

        return (
            priority,
            match.confidence_score,
            match.source_count,
            latest_ts,
            found_boost,
        )

    return sorted(matches, key=sort_key, reverse=True)


def _is_exact_document_match(match: PersonMatch, query: str) -> bool:
    if match.document_id_hash:
        try:
            return match.document_id_hash == hash_document_id(query)
        except ValueError:
            pass

    if match.document_id_last4:
        try:
            query_digits = normalize_document_id(query)
            return query_digits.endswith(match.document_id_last4) and match.confidence_score >= 100.0
        except ValueError:
            pass

    return match.confidence_score >= 100.0


def document_hash_from_id(document_id: str | None) -> str | None:
    if not document_id:
        return None
    try:
        return hash_document_id(document_id)
    except ValueError:
        return None
