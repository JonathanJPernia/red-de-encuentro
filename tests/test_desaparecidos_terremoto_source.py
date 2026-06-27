import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.config import get_settings
from app.database import SessionLocal
from app.services.search_service import SearchService
from app.sources.desaparecidos_terremoto_venezuela_source import (
    DesaparecidosTerremotoVenezuelaSource,
)


SAMPLE_RESPONSE = {
    "items": [
        {
            "id": 42,
            "nombre": "Juan Carlos Pérez",
            "cedula": "V-12.345.678",
            "estado": "localizado",
            "fecha": "2026-06-27T10:00:00Z",
            "estadoUbicacion": "La Guaira",
            "municipio": "Vargas",
            "telefonoContacto": "04141234567",
            "nombreContacto": "María Pérez",
            "correoContacto": "test@example.com",
            "direccion": "Av. Secreta 123",
            "foto": "https://example.com/foto.jpg",
            "fechaNacimiento": "1990-01-01",
            "localizadoPor": "Familiar",
            "localizadoNota": "Nota privada",
        },
        {
            "id": 43,
            "nombre": "Ana López",
            "estado": "sin-contacto",
            "createdAt": "2026-06-26T15:30:00Z",
        },
    ],
    "total": 2,
}


def _make_source() -> DesaparecidosTerremotoVenezuelaSource:
    source = DesaparecidosTerremotoVenezuelaSource.__new__(DesaparecidosTerremotoVenezuelaSource)
    source.api_base_url = "https://desaparecidos-terremoto-api.theempire.tech"
    source.public_base_url = "https://desaparecidosterremotovenezuela.com"
    source.timeout = 10
    return source


def test_maps_items_correctly() -> None:
    source = _make_source()
    source._fetch_search = MagicMock(return_value=SAMPLE_RESPONSE)

    matches = source.search("Juan")

    assert len(matches) == 2
    assert matches[0].full_name == "Juan Carlos Pérez"
    assert matches[0].document_id_last4 == "5678"
    assert matches[0].sources[0].source_url == (
        "https://desaparecidosterremotovenezuela.com/personas/42"
    )


def test_localizado_maps_to_found() -> None:
    source = _make_source()
    source._fetch_search = MagicMock(return_value={"items": [SAMPLE_RESPONSE["items"][0]]})
    matches = source.search("Juan")
    assert matches[0].sources[0].status == "found"


def test_sin_contacto_maps_to_missing() -> None:
    source = _make_source()
    source._fetch_search = MagicMock(return_value={"items": [SAMPLE_RESPONSE["items"][1]]})
    matches = source.search("Ana")
    assert matches[0].sources[0].status == "missing"


def test_does_not_expose_sensitive_fields() -> None:
    source = _make_source()
    source._fetch_search = MagicMock(return_value={"items": [SAMPLE_RESPONSE["items"][0]]})
    matches = source.search("Juan")
    payload = json.dumps(matches[0].model_dump(mode="json"))

    assert "04141234567" not in payload
    assert "12345678" not in payload
    assert "Av. Secreta" not in payload
    assert "test@example.com" not in payload
    assert "foto.jpg" not in payload
    assert "raw_data" not in payload


def test_only_requests_first_page() -> None:
    source = _make_source()
    with patch.object(source, "_get_json", return_value=SAMPLE_RESPONSE) as mock_get:
        source.search("juan")

    mock_get.assert_called_once_with(
        "/api/personas",
        params={"page": 1, "pageSize": 10, "q": "juan"},
    )


def test_failure_does_not_break_search(db_session, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ENABLE_EXTERNAL_SOURCES", "true")
    monkeypatch.setenv("ENABLE_DESAPARECIDOS_TERREMOTO_VENEZUELA", "true")
    get_settings.cache_clear()

    with patch.object(
        DesaparecidosTerremotoVenezuelaSource,
        "search",
        side_effect=httpx.HTTPStatusError(
            "403",
            request=httpx.Request("GET", "https://example.com"),
            response=httpx.Response(403),
        ),
    ):
        response = SearchService(db_session).search("zzzz-no-local-match-zzzz")

    assert isinstance(response.matches, list)


def test_does_not_store_full_cedula_in_match() -> None:
    source = _make_source()
    source._fetch_search = MagicMock(return_value={"items": [SAMPLE_RESPONSE["items"][0]]})
    matches = source.search("12345678")
    assert matches[0].document_id_last4 == "5678"
    assert "12345678" not in json.dumps(matches[0].model_dump(mode="json"))
