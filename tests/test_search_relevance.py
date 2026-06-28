import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.schemas.search import PersonMatch, SourceMatch
from app.services.match_consolidation import rank_matches
from app.services.name_matching import (
    SCORE_ALL_TOKENS,
    SCORE_TWO_TOKEN_ONE_MATCH_MAX,
    SCORE_TWO_TOKEN_ONE_MATCH_FUZZY_MAX,
    score_name_match,
)
from app.services.search_service import SearchService
from app.sources.localizados_venezuela_source import LocalizadosVenezuelaSource
from app.sources.parsers.remix_data_parser import parse_remix_root_data
from app.sources.venezuela_te_busca_source import VenezuelaTeBuscaSource


@pytest.fixture
def client():
    return TestClient(app)


def _localizados_match(full_name: str, confidence: float = 80.0) -> PersonMatch:
    return PersonMatch(
        full_name=full_name,
        confidence_score=confidence,
        sources=[
            SourceMatch(
                name="Localizados Venezuela",
                status="found",
                source_url="https://localizadosvenezuela.com/example",
            )
        ],
    )


def test_mariangeles_perez_exact_scores_100() -> None:
    assert score_name_match("Mariangeles Perez", "Mariangeles Perez") == SCORE_ALL_TOKENS


def test_mariangeles_perez_single_token_match_capped_at_65() -> None:
    score = score_name_match("Mariangeles Perez", "Perez Jesus")
    assert score is not None
    assert score <= SCORE_TWO_TOKEN_ONE_MATCH_MAX


def test_mariangeles_perez_does_not_score_perez_only_at_90() -> None:
    score = score_name_match("Mariangeles Perez", "Perez Jesus")
    assert score is None or score < 90


def test_zero_common_tokens_discarded_for_mariangeles() -> None:
    assert score_name_match("Mariangeles Perez", "Ramos Vargas Emily Estefania") is None


def test_maria_perez_partial_for_mariangeles_query() -> None:
    score = score_name_match("Mariangeles Perez", "Maria Perez")
    assert score is not None
    assert score <= SCORE_TWO_TOKEN_ONE_MATCH_FUZZY_MAX


def test_juan_perez_never_matches_emily() -> None:
    assert score_name_match("Juan Perez", "Emily Estefanía Ramos Vargas") is None


def test_localizados_partial_matches_filtered_from_search(db_session, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ENABLE_EXTERNAL_SOURCES", "true")
    monkeypatch.setenv("ENABLE_LOCALIZADOS_VENEZUELA", "true")
    get_settings.cache_clear()

    partial_matches = [
        _localizados_match("Pérez Jesús"),
        _localizados_match("Perez Rawson"),
        _localizados_match("Mariangeles Perez", confidence=100.0),
    ]

    with patch.object(LocalizadosVenezuelaSource, "search", return_value=partial_matches):
        response = SearchService(db_session).search("Mariangeles Perez")

    names = [match.full_name for match in response.matches]
    assert "Mariangeles Perez" in names
    assert "Pérez Jesús" not in names
    assert "Perez Rawson" not in names
    mariangeles = next(m for m in response.matches if m.full_name == "Mariangeles Perez")
    assert mariangeles.confidence_score == SCORE_ALL_TOKENS


def test_ambiguous_two_token_search_raises_when_only_weak_matches(db_session, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ENABLE_EXTERNAL_SOURCES", "true")
    monkeypatch.setenv("ENABLE_LOCALIZADOS_VENEZUELA", "true")
    get_settings.cache_clear()

    # Scores 70-79: pasan umbral 70 pero disparan mensaje de búsqueda ambigua.
    borderline = [
        _localizados_match("Maria Perez"),
    ]

    with patch.object(LocalizadosVenezuelaSource, "search", return_value=borderline):
        with patch("app.services.search_service.score_name_match", return_value=75.0):
            with pytest.raises(ValueError, match="demasiado amplia"):
                SearchService(db_session).search("Mariangeles Perez")


def test_debug_without_admin_secret_returns_403(client, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_SECRET", "debug-secret")
    get_settings.cache_clear()

    response = client.get("/search", params={"q": "Juan Perez", "debug": "true"})
    assert response.status_code == 403


def test_debug_without_admin_secret_omits_debug_field(client, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ENABLE_EXTERNAL_SOURCES", "false")
    get_settings.cache_clear()

    response = client.get("/search", params={"q": "Juan"})
    assert response.status_code in {200, 400}
    if response.status_code == 200:
        assert "debug" not in response.json()


def test_debug_with_admin_secret_shows_provider_stats(client, db_session, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_SECRET", "debug-secret")
    monkeypatch.setenv("ENABLE_EXTERNAL_SOURCES", "true")
    monkeypatch.setenv("ENABLE_LOCALIZADOS_VENEZUELA", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "super-secret-token")
    get_settings.cache_clear()

    with patch.object(
        LocalizadosVenezuelaSource,
        "search",
        return_value=[_localizados_match("Mariangeles Perez", confidence=100.0)],
    ):
        response = client.get(
            "/search",
            params={"q": "Mariangeles Perez", "debug": "true", "secret": "debug-secret"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert "debug" in payload
    providers = payload["debug"]["providers"]
    assert any(p["name"] == "Localizados Venezuela" for p in providers)
    localizados = next(p for p in providers if p["name"] == "Localizados Venezuela")
    assert localizados["mapped_count"] >= 1
    assert localizados["filtered_count"] >= 1
    serialized = json.dumps(payload)
    assert "super-secret-token" not in serialized
    assert "debug-secret" not in serialized


def test_source_count_does_not_beat_textual_relevance() -> None:
    high_relevance = PersonMatch(
        full_name="Mariangeles Perez",
        confidence_score=100.0,
        source_count=1,
        sources=[SourceMatch(name="A", status="found")],
    )
    low_relevance_many_sources = PersonMatch(
        full_name="Perez Jesus",
        confidence_score=65.0,
        source_count=5,
        sources=[SourceMatch(name=f"S{i}", status="found") for i in range(5)],
    )

    ranked = rank_matches([low_relevance_many_sources, high_relevance], "Mariangeles Perez")
    assert ranked[0].full_name == "Mariangeles Perez"


def test_venezuela_te_busca_parser_extracts_mariangeles() -> None:
    fixture = json.dumps(
        {
            "data": {
                "persons": [
                    {
                        "id": "mariangeles-1",
                        "firstName": "Mariangeles",
                        "lastName": "Perez",
                        "status": "missing",
                    }
                ]
            }
        }
    )
    persons = parse_remix_root_data(fixture)
    assert any(p.get("firstName") == "Mariangeles" for p in persons)


def test_venezuela_te_busca_retries_normalized_query() -> None:
    source = VenezuelaTeBuscaSource.__new__(VenezuelaTeBuscaSource)
    source.base_url = "https://venezuelatebusca.com"
    source.timeout = 10
    source.last_search_stats = VenezuelaTeBuscaSource().last_search_stats

    calls: list[str] = []

    def fake_fetch(query: str) -> str:
        calls.append(query)
        if query == "Mariangeles Perez":
            return json.dumps({"data": {"persons": []}})
        return json.dumps(
            {
                "data": {
                    "persons": [
                        {
                            "id": "1",
                            "firstName": "Mariangeles",
                            "lastName": "Perez",
                            "status": "missing",
                        }
                    ]
                }
            }
        )

    source._fetch_root_data = fake_fetch  # type: ignore[method-assign]

    persons = source._fetch_persons("Mariangeles Perez")
    assert len(persons) == 1
    assert persons[0]["firstName"] == "Mariangeles"
    assert calls == ["Mariangeles Perez", "mariangeles perez"]


def test_venezuela_te_busca_search_uses_root_data_query_param() -> None:
    source = VenezuelaTeBuscaSource.__new__(VenezuelaTeBuscaSource)
    source.base_url = "https://venezuelatebusca.com"
    source.timeout = 10
    source.last_search_stats = VenezuelaTeBuscaSource().last_search_stats

    with patch.object(source, "_get_text", return_value=json.dumps({"data": {"persons": []}})) as mock_get:
        source.search("Mariangeles Perez")

    mock_get.assert_any_call("/_root.data", params={"query": "Mariangeles Perez"})
