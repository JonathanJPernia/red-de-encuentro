import logging

import pytest
from fastapi.testclient import TestClient

from app.bot.rate_limit import InMemoryRateLimiter
from app.bot.response_format import format_bot_match, needs_more_specific_query
from app.main import app
from app.schemas.search import PersonMatch, SourceMatch
from app.services.privacy_log import mask_query_for_log
from app.services.query_validation import validate_search_query
from app.sources.health import get_sources_health


def test_rate_limit_blocks_after_max_calls() -> None:
    limiter = InMemoryRateLimiter(max_calls=3, period_seconds=60)
    key = "user-123"

    assert limiter.is_allowed(key) is True
    assert limiter.is_allowed(key) is True
    assert limiter.is_allowed(key) is True
    assert limiter.is_allowed(key) is False


@pytest.mark.parametrize(
    "query,message",
    [
        ("", "vacía"),
        ("a", "genérica"),
        ("de", "genérica"),
        ("ab", "3 caracteres"),
        ("1234", "5 dígitos"),
    ],
)
def test_invalid_queries_raise(query: str, message: str) -> None:
    with pytest.raises(ValueError):
        validate_search_query(query)


def test_valid_name_and_document_queries() -> None:
    assert validate_search_query("Juan Pérez") == "Juan Pérez"
    assert validate_search_query("123456") == "123456"


def test_mask_query_for_log_document() -> None:
    assert mask_query_for_log("12345678") == "***5678"
    assert mask_query_for_log("V-12345678") == "***5678"


def test_mask_query_for_log_name() -> None:
    assert mask_query_for_log("Juan Pérez") == "Juan Pérez"


def test_search_service_logs_masked_document(caplog) -> None:
    from app.database import SessionLocal
    from app.services.search_service import SearchService

    caplog.set_level(logging.INFO, logger="app.services.search_service")
    db = SessionLocal()
    try:
        SearchService(db).search("12345678")
    finally:
        db.close()

    logged = " ".join(
        record.message
        for record in caplog.records
        if record.name == "app.services.search_service"
    )
    assert "12345678" not in logged
    assert "***5678" in logged


def test_sources_health_does_not_expose_secrets(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_EXTERNAL_SOURCES", "true")
    monkeypatch.setenv("RED_AYUDA_SUPABASE_ANON_KEY", "super-secret-anon-key")
    monkeypatch.setenv("EMERGENCIA_JOCH_SUPABASE_ANON_KEY", "another-secret")

    from app.config import get_settings

    get_settings.cache_clear()
    payload = get_sources_health()
    text = str(payload)

    assert "super-secret-anon-key" not in text
    assert "another-secret" not in text
    assert payload["sources"]
    for item in payload["sources"]:
        assert set(item.keys()) == {"name", "enabled", "configured", "status", "estado"}


def test_sources_health_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/sources/health")
    assert response.status_code == 200
    assert "sources" in response.json()


def test_bot_format_does_not_show_raw_data() -> None:
    match = PersonMatch(
        full_name="Juan Pérez",
        document_id_last4="5678",
        confidence_score=95.0,
        status="missing",
        source_count=1,
        sources=[
            SourceMatch(
                name="Fuente Test",
                status="missing",
                source_url="https://example.com/x",
                published_at=None,
            )
        ],
    )
    text = format_bot_match(1, match)
    assert "raw_data" not in text
    assert "5678" not in text
    assert "Nombre: Juan Pérez" in text
    assert "Estado: Desaparecido/a (según fuente)" in text
    assert "Fuentes encontradas: 1" in text
    assert "Enlace (Fuente Test):" in text
    assert "missing" not in text


def test_needs_more_specific_query() -> None:
    low = [
        PersonMatch(full_name="A", confidence_score=80.0, sources=[]),
        PersonMatch(full_name="B", confidence_score=82.0, sources=[]),
    ]
    high = [
        PersonMatch(full_name="A", confidence_score=95.0, sources=[]),
        PersonMatch(full_name="B", confidence_score=96.0, sources=[]),
    ]
    assert needs_more_specific_query(low) is True
    assert needs_more_specific_query(high) is False
