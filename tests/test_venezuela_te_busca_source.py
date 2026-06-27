import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.config import get_settings
from app.services.search_service import SearchService
from app.sources.parsers.remix_data_parser import parse_remix_root_data
from app.sources.venezuela_te_busca_source import (
    VenezuelaTeBuscaSource,
    _build_safe_raw_data,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "venezuela_te_busca_root_data.json"


def _fixture_text() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def _make_source() -> VenezuelaTeBuscaSource:
    source = VenezuelaTeBuscaSource.__new__(VenezuelaTeBuscaSource)
    source.base_url = "https://venezuelatebusca.com"
    source.timeout = 10
    return source


def test_parser_extracts_persons_from_fixture() -> None:
    persons = parse_remix_root_data(_fixture_text())
    assert len(persons) >= 1
    assert any(p.get("firstName") for p in persons)


def test_parser_maps_first_and_last_name() -> None:
    persons = parse_remix_root_data(_fixture_text())
    quintero = next(p for p in persons if p.get("lastName") == "Quintero")
    assert quintero["firstName"] == "Juan"


def test_source_maps_full_name() -> None:
    source = _make_source()
    source._fetch_root_data = MagicMock(return_value=_fixture_text())

    matches = source.search("juan")
    names = {match.full_name for match in matches}

    assert "Juan Quintero" in names
    assert matches[0].sources[0].name == "Venezuela Te Busca"
    assert matches[0].sources[0].source_url == "https://venezuelatebusca.com/?query=juan"


def test_id_number_is_masked_not_exposed() -> None:
    source = _make_source()
    source._fetch_root_data = MagicMock(return_value=_fixture_text())

    matches = source.search("Pantoja")
    pantoja = next(m for m in matches if "Pantoja" in m.full_name)

    assert pantoja.document_id_last4 == "1348"
    payload = json.dumps(pantoja.model_dump(mode="json"))
    assert "28441348" not in payload


def test_reporter_contact_not_in_raw_data_or_response() -> None:
    person = {
        "id": "test-id",
        "firstName": "María",
        "lastName": "López",
        "status": "missing",
        "reporter": {"name": "Pedro", "phone": "04141234567", "email": "pedro@example.com"},
    }
    raw_data = _build_safe_raw_data(person)

    assert raw_data is not None
    assert "reporter" not in raw_data
    assert "04141234567" not in json.dumps(raw_data)
    assert "pedro@example.com" not in json.dumps(raw_data)

    source = _make_source()
    source._fetch_root_data = MagicMock(
        return_value=json.dumps(
            {
                "data": {
                    "persons": [
                        {
                            "id": "x",
                            "firstName": "María",
                            "lastName": "López",
                            "status": "missing",
                            "reporter": {
                                "name": "Pedro",
                                "phone": "04141234567",
                                "email": "pedro@example.com",
                            },
                        }
                    ]
                }
            }
        )
    )
    matches = source.search("maria")
    payload = json.dumps([m.model_dump(mode="json") for m in matches])
    assert "04141234567" not in payload
    assert "pedro@example.com" not in payload
    assert "reporter" not in payload


def test_only_uses_get_without_page_param() -> None:
    source = _make_source()
    with patch.object(source, "_get_text", return_value=_fixture_text()) as mock_get:
        source.search("juan")

    mock_get.assert_called_once_with("/_root.data", params={"query": "juan"})
    assert "page" not in (mock_get.call_args.kwargs.get("params") or {})


def test_does_not_post() -> None:
    source = _make_source()
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = _fixture_text()
    mock_response.raise_for_status = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response
    mock_client.post = MagicMock(side_effect=AssertionError("POST no permitido"))

    with patch("app.sources.venezuela_te_busca_source.httpx.Client", return_value=mock_client):
        source.search("juan")

    mock_client.get.assert_called()
    mock_client.post.assert_not_called()


def test_status_missing_and_found_mapping() -> None:
    source = _make_source()
    source._fetch_root_data = MagicMock(return_value=_fixture_text())

    matches = source.search("juan")
    by_name = {m.full_name: m.sources[0].status for m in matches}

    assert by_name["Juan Quintero"] == "missing"
    assert by_name["Juan Castro"] == "found"


def test_parser_failure_does_not_break_search_service(db_session, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ENABLE_EXTERNAL_SOURCES", "true")
    monkeypatch.setenv("ENABLE_VENEZUELA_TE_BUSCA", "true")
    get_settings.cache_clear()

    with patch.object(
        VenezuelaTeBuscaSource,
        "search",
        side_effect=ValueError("parser exploded"),
    ):
        response = SearchService(db_session).search("zzzz-no-local-match-zzzz")

    assert isinstance(response.matches, list)


def test_safe_search_handles_parser_exception() -> None:
    source = _make_source()
    source._fetch_root_data = MagicMock(return_value="not-json")

    with patch(
        "app.sources.venezuela_te_busca_source.parse_remix_root_data",
        side_effect=RuntimeError("boom"),
    ):
        matches = source.safe_search("juan")

    assert matches == []
