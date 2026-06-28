"""Scoring centralizado para coincidencias por nombre o documento."""

from __future__ import annotations

from app.services.name_matching import score_name_match
from app.services.normalize_service import is_document_query, normalize_document_id


def score_query_match(query: str, full_name: str, document_id: str | None = None) -> float:
    if is_document_query(query) and document_id:
        if normalize_document_id(query) == normalize_document_id(document_id):
            return 100.0

    score = score_name_match(query, full_name)
    return score if score is not None else 0.0
