import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.config import get_settings
from app.schemas.search import PersonMatch
from app.services.search_service import SearchService
from app.sources.emergencia_joch_source import EmergenciaJochSource
from app.sources.red_ayuda_venezuela_source import RedAyudaVenezuelaSource, build_payload
from app.sources.supabase_client import SupabaseClient


def test_build_payload_red_ayuda() -> None:
    assert build_payload("juan") == {"q": "juan"}


def test_red_ayuda_maps_supabase_response() -> None:
    source = RedAyudaVenezuelaSource.__new__(RedAyudaVenezuelaSource)
    source.client = MagicMock()
    source.client.post.return_value = [
        {
            "name": "Maria Pinto",
            "category": "hospital",
            "label": "En un hospital",
            "loc": "Periférico de Pariata",
            "detail": "20 años — C.I. 30.986.536 — sector Playa Grande",
            "photo_url": "https://example.com/photo.jpg",
            "slug": "maria-pinto",
        }
    ]

    matches = source.search("Maria")
    assert len(matches) == 1
    assert matches[0].full_name == "Maria Pinto"
    assert matches[0].document_id_last4 == "6536"
    assert matches[0].sources[0].name == "Red Ayuda Venezuela"
    payload = json.dumps(matches[0].model_dump(mode="json"))
    assert "30986536" not in payload
    assert "loc" not in payload


def test_joch_does_not_expose_sensitive_fields() -> None:
    source = EmergenciaJochSource.__new__(EmergenciaJochSource)
    source.client = MagicMock()
    source.client.get.return_value = [
        {
            "id": 2,
            "nombre_completo": "Francys Arocha (CI: V-11.144.145)",
            "estado_persona": "Desaparecido",
            "detalles_emergencia": "Última vez vista en edificio",
            "created_at": "2026-06-25T16:08:43.480409+00:00",
            "direccion_exacta": "Caraballeda secreta",
            "reportado_por_telefono": "04141234567",
        }
    ]

    matches = source.search("Francys")
    payload = json.dumps(matches[0].model_dump(mode="json"))
    assert "11144145" not in payload
    assert "Caraballeda" not in payload
    assert "04141234567" not in payload
    assert matches[0].full_name == "Francys Arocha"


def test_external_source_failure_does_not_break_search(db_session, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ENABLE_EXTERNAL_SOURCES", "true")
    monkeypatch.setenv("RED_AYUDA_SUPABASE_ANON_KEY", "test-key")
    monkeypatch.setenv("EMERGENCIA_JOCH_SUPABASE_ANON_KEY", "test-key")
    get_settings.cache_clear()

    with patch.object(RedAyudaVenezuelaSource, "search", side_effect=TimeoutError("timeout")):
        with patch.object(
            EmergenciaJochSource,
            "search",
            return_value=[
                PersonMatch(
                    full_name="Remoto Test",
                    document_id_last4="9999",
                    confidence_score=95.0,
                    sources=[],
                )
            ],
        ):
            service = SearchService(db_session)
            response = service.search("zzzz-no-local-match-zzzz")
            assert any(match.full_name == "Remoto Test" for match in response.matches)


def test_supabase_client_timeout_raises_after_retry() -> None:
    client = SupabaseClient("https://example.supabase.co", "anon-key", timeout=0.01)

    with patch("app.sources.supabase_client.httpx.Client") as mock_client:
        instance = mock_client.return_value.__enter__.return_value
        instance.request.side_effect = httpx.TimeoutException("timeout")

        with pytest.raises(httpx.TimeoutException):
            client.get("/rest/v1/test")

        assert instance.request.call_count == 2
