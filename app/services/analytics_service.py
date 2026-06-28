from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.search_log import SearchLog
from app.services.normalize_service import is_document_query, normalize_name
from app.services.privacy_log import mask_query_for_log

logger = logging.getLogger(__name__)

SearchSource = Literal["telegram", "api"]
TOP_QUERIES_LIMIT = 10


def hash_user_identifier(source: SearchSource, identifier: str | None) -> str | None:
    if not identifier:
        return None
    payload = f"{source}:{identifier.strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prepare_query_analytics(query: str) -> tuple[str, str]:
    stripped = query.strip()
    if is_document_query(stripped):
        query_masked = mask_query_for_log(stripped)
    else:
        query_masked = normalize_name(stripped)

    if not query_masked:
        query_masked = "***"

    query_hash = hashlib.sha256(query_masked.encode("utf-8")).hexdigest()
    return query_masked, query_hash


def log_search(
    db: Session,
    *,
    source: SearchSource,
    query: str,
    results_count: int,
    response_ms: int,
    success: bool,
    error_type: str | None = None,
    user_identifier: str | None = None,
) -> None:
    try:
        query_masked, query_hash = prepare_query_analytics(query)
        user_hash = hash_user_identifier(source, user_identifier)

        entry = SearchLog(
            source=source,
            user_hash=user_hash,
            query_hash=query_hash,
            query_masked=query_masked,
            results_count=max(results_count, 0),
            response_ms=max(response_ms, 0),
            success=success,
            error_type=error_type,
        )
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("No se pudo registrar analytics de búsqueda")


def get_admin_stats(db: Session, days: int = 7) -> dict:
    period_days = max(days, 1)
    since = datetime.now(timezone.utc) - timedelta(days=period_days)

    logs = db.scalars(select(SearchLog).where(SearchLog.created_at >= since)).all()
    if not logs:
        return {
            "period_days": period_days,
            "total_searches": 0,
            "unique_users": 0,
            "telegram_searches": 0,
            "api_searches": 0,
            "successful_searches": 0,
            "empty_results": 0,
            "average_response_ms": 0,
            "top_queries": [],
            "searches_by_day": [],
            "recent_errors": [],
        }

    total = len(logs)
    user_hashes = {log.user_hash for log in logs if log.user_hash}
    telegram_count = sum(1 for log in logs if log.source == "telegram")
    api_count = sum(1 for log in logs if log.source == "api")
    successful = sum(1 for log in logs if log.success)
    empty_results = sum(1 for log in logs if log.success and log.results_count == 0)
    average_ms = round(sum(log.response_ms for log in logs) / total)

    query_counts: dict[str, int] = {}
    for log in logs:
        query_counts[log.query_masked] = query_counts.get(log.query_masked, 0) + 1

    top_queries = [
        {"query": query, "count": count}
        for query, count in sorted(query_counts.items(), key=lambda item: (-item[1], item[0]))[
            :TOP_QUERIES_LIMIT
        ]
    ]

    day_counts: dict[str, int] = {}
    for log in logs:
        day_key = log.created_at.astimezone(timezone.utc).date().isoformat()
        day_counts[day_key] = day_counts.get(day_key, 0) + 1

    searches_by_day = [
        {"date": day, "count": count}
        for day, count in sorted(day_counts.items())
    ]

    recent_errors = [
        {
            "created_at": log.created_at.astimezone(timezone.utc).isoformat(),
            "source": log.source,
            "query_masked": log.query_masked,
            "error_type": log.error_type or "unknown",
        }
        for log in sorted(
            [entry for entry in logs if not entry.success],
            key=lambda entry: entry.created_at,
            reverse=True,
        )[:10]
    ]

    return {
        "period_days": period_days,
        "total_searches": total,
        "unique_users": len(user_hashes),
        "telegram_searches": telegram_count,
        "api_searches": api_count,
        "successful_searches": successful,
        "empty_results": empty_results,
        "average_response_ms": average_ms,
        "top_queries": top_queries,
        "searches_by_day": searches_by_day,
        "recent_errors": recent_errors,
    }
