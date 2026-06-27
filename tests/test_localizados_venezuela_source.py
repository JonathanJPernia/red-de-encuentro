import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.config import get_settings
from app.database import SessionLocal
from app.services.search_service import SearchService
from app.sources.localizados_venezuela_source import LocalizadosVenezuelaSource


SAMPLE_RESPONSE = {
    "data": [
        {
            "slug": "rodriguez-juan-lygc5g",
            "nombreCompleto": "Rodriguez Juan",
            "edad": "28",
            "direccion": "La Guaira",
            "observaciones": "CI: V-30.986.536 · contacto 04141234567",
            "condicion": "desconocido",
            "lugarSlug": "hospital-universitario-de-caracas",
            "lugarNombre": "Hospital Universitario de Caracas",
            "fuente": {
                "tipo": "ocr",
                "nombre": "consolidado.csv",
                "notas": "detalle interno",
                "fecha": "2026-06-27",
            },
            "publicadoEn": "2026-06-27T12:58:52.495Z",
        }
    ],
    "meta": {"page": 1, "limit": 10, "total": 1, "totalPages": 1},
}


def test_localizados_maps_results_correctly() -> None:
    source = LocalizadosVenezuelaSource.__new__(LocalizadosVenezuelaSource)
    source.base_url = "https://localizadosvenezuela.com"
    source.timeout = 10
    source._fetch_search = MagicMock(return_value=SAMPLE_RESPONSE)

    matches = source.search("Juan")

    assert len(matches) == 1
    assert matches[0].full_name == "Rodriguez Juan"
    assert matches[0].sources[0].status == "found"
    assert matches[0].sources[0].name == "Localizados Venezuela"
    assert matches[0].sources[0].source_url == (
        "https://localizadosvenezuela.com/localizados/rodriguez-juan-lygc5g"
    )
    assert matches[0].document_id_last4 == "6536"


def test_localizados_status_is_found() -> None:
    source = LocalizadosVenezuelaSource.__new__(LocalizadosVenezuelaSource)
    source.base_url = "https://localizadosvenezuela.com"
    source.timeout = 10
    source._fetch_search = MagicMock(return_value=SAMPLE_RESPONSE)

    matches = source.search("Rodriguez")
    assert all(match.sources[0].status == "found" for match in matches)


def test_localizados_does_not_use_rsc_urls() -> None:
    source = LocalizadosVenezuelaSource.__new__(LocalizadosVenezuelaSource)
    source.base_url = "https://localizadosvenezuela.com"
    source.timeout = 10

    with patch.object(source, "_get_json", return_value=SAMPLE_RESPONSE) as mock_get:
        source.search("juan")

    mock_get.assert_called_once_with(
        "/api/v1/localizados",
        params={"q": "juan", "page": 1, "limit": 10},
    )
    assert "_rsc" not in mock_get.call_args[0][0]


def test_localizados_does_not_expose_sensitive_raw_data() -> None:
    source = LocalizadosVenezuelaSource.__new__(LocalizadosVenezuelaSource)
    source.base_url = "https://localizadosvenezuela.com"
    source.timeout = 10
    source._fetch_search = MagicMock(return_value=SAMPLE_RESPONSE)

    matches = source.search("Juan")
    payload = json.dumps(matches[0].model_dump(mode="json"))

    assert "04141234567" not in payload
    assert "30986536" not in payload
    assert "La Guaira" not in payload
    assert "observaciones" not in payload
    assert "raw_data" not in payload


def test_localizados_failure_does_not_break_search(db_session, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ENABLE_EXTERNAL_SOURCES", "true")
    monkeypatch.setenv("ENABLE_LOCALIZADOS_VENEZUELA", "true")
    get_settings.cache_clear()

    with patch.object(
        LocalizadosVenezuelaSource,
        "search",
        side_effect=httpx.TimeoutException("timeout"),
    ):
        service = SearchService(db_session)
        response = service.search("zzzz-no-local-match-zzzz")

    assert isinstance(response.matches, list)
