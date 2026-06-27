from app.schemas.search import PersonMatch, SearchResponse, SourceMatch
from app.services.status_labels import (
    INFORMATIONAL_DISCLAIMER,
    format_source_health_status_es,
    format_status_es,
)


def test_format_status_es_missing() -> None:
    assert format_status_es("missing") == "Desaparecido/a (según fuente)"


def test_format_status_es_found() -> None:
    assert format_status_es("found") == "Localizado/a (según fuente)"


def test_person_match_exposes_estado() -> None:
    match = PersonMatch(
        full_name="Juan Pérez",
        confidence_score=95.0,
        status="missing",
        sources=[
            SourceMatch(
                name="Fuente Test",
                status="found",
                source_url="https://example.com",
            )
        ],
    )
    payload = match.model_dump()
    assert payload["estado"] == "Desaparecido/a (según fuente)"
    assert payload["sources"][0]["estado"] == "Localizado/a (según fuente)"


def test_search_response_includes_disclaimer() -> None:
    response = SearchResponse(query="juan", matches=[])
    assert response.disclaimer == INFORMATIONAL_DISCLAIMER


def test_source_health_status_labels() -> None:
    assert format_source_health_status_es("ready") == "Operativa"
    assert format_source_health_status_es("disabled") == "Desactivada"
