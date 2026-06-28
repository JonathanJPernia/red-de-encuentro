from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.schemas.search import PersonMatch
from app.sources.http_debug import detect_block_reason
from app.sources.localizados_venezuela_source import LocalizadosVenezuelaSource
from app.sources.source_health_manager import (
    DEGRADED_TTL_MINUTES,
    get_status,
    record_failure,
    record_success,
    should_skip,
)
from app.sources.health import get_sources_health


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


def _cloudflare_response(*, status: int = 403) -> httpx.Response:
    request = httpx.Request("GET", "https://example.com/_root.data")
    return httpx.Response(
        status,
        headers={"server": "cloudflare", "cf-mitigated": "challenge"},
        text="Just a moment...",
        request=request,
    )


def test_detect_cloudflare_challenge_by_headers() -> None:
    assert detect_block_reason(response=_cloudflare_response()) == "cloudflare_challenge"


def test_detect_cloudflare_challenge_by_body() -> None:
    request = httpx.Request("GET", "https://example.com/")
    response = httpx.Response(
        503,
        text="Please wait... challenges.cloudflare.com",
        request=request,
    )
    assert detect_block_reason(response=response) == "cloudflare_challenge"


def test_detect_forbidden_and_rate_limited() -> None:
    request = httpx.Request("GET", "https://example.com/")
    forbidden = httpx.Response(403, text="Forbidden", request=request)
    limited = httpx.Response(429, text="Too Many Requests", request=request)
    assert detect_block_reason(response=forbidden) == "forbidden"
    assert detect_block_reason(response=limited) == "rate_limited"


def test_detect_timeout_from_exception() -> None:
    assert detect_block_reason(exc=httpx.TimeoutException("timeout")) == "timeout"


def test_record_failure_marks_degraded_with_ttl() -> None:
    fixed = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
    with patch("app.sources.source_health_manager._utcnow", return_value=fixed):
        record_failure("Venezuela Te Busca", "blocked", reason="cloudflare_challenge")

    status = get_status("Venezuela Te Busca")
    assert status["status"] == "degraded"
    assert status["reason"] == "cloudflare_challenge"
    assert status["consecutive_failures"] == 1
    expected_until = fixed + timedelta(minutes=DEGRADED_TTL_MINUTES["cloudflare_challenge"])
    assert status["degraded_until"] == expected_until


def test_should_skip_true_while_degraded_until_in_future() -> None:
    start = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
    with patch("app.sources.source_health_manager._utcnow", return_value=start):
        record_failure("Venezuela Te Busca", "blocked", reason="cloudflare_challenge")

    mid = start + timedelta(minutes=5)
    with patch("app.sources.source_health_manager._utcnow", return_value=mid):
        assert should_skip("Venezuela Te Busca") is True


def test_should_skip_false_after_ttl_expires() -> None:
    start = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
    with patch("app.sources.source_health_manager._utcnow", return_value=start):
        record_failure("Venezuela Te Busca", "blocked", reason="timeout")

    after = start + timedelta(minutes=DEGRADED_TTL_MINUTES["timeout"] + 1)
    with patch("app.sources.source_health_manager._utcnow", return_value=after):
        assert should_skip("Venezuela Te Busca") is False


def test_record_success_clears_degraded_state() -> None:
    record_failure("Localizados Venezuela", "403", reason="forbidden")
    record_success("Localizados Venezuela")
    status = get_status("Localizados Venezuela")
    assert status["status"] == "healthy"
    assert status["reason"] is None
    assert status["degraded_until"] is None
    assert status["consecutive_failures"] == 0


def test_rate_limited_uses_ten_minute_ttl() -> None:
    fixed = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
    with patch("app.sources.source_health_manager._utcnow", return_value=fixed):
        record_failure("Red Ayuda Venezuela", "429", reason="rate_limited")
    status = get_status("Red Ayuda Venezuela")
    assert status["degraded_until"] == fixed + timedelta(minutes=10)


def test_timeout_uses_two_minute_ttl() -> None:
    fixed = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
    with patch("app.sources.source_health_manager._utcnow", return_value=fixed):
        record_failure("Emergencia Joch.dev", "timeout", reason="timeout")
    status = get_status("Emergencia Joch.dev")
    assert status["degraded_until"] == fixed + timedelta(minutes=2)


def test_safe_search_skips_degraded_without_calling_search() -> None:
    start = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
    with patch("app.sources.source_health_manager._utcnow", return_value=start):
        record_failure("Localizados Venezuela", "403", reason="cloudflare_challenge")

    source = LocalizadosVenezuelaSource.__new__(LocalizadosVenezuelaSource)
    source.source_name = "Localizados Venezuela"
    source.last_search_stats = LocalizadosVenezuelaSource().last_search_stats
    source.search = MagicMock(return_value=[PersonMatch(full_name="X", confidence_score=100.0, sources=[])])

    with patch.object(source, "is_configured", return_value=True):
        with patch("app.sources.source_health_manager._utcnow", return_value=start + timedelta(minutes=1)):
            matches = source.safe_search("Juan")

    assert matches == []
    source.search.assert_not_called()
    assert source.last_search_stats.skipped is True
    assert source.last_search_stats.provider_status == "degraded"
    assert source.last_search_stats.reason == "cloudflare_challenge"


def test_sources_health_shows_degraded_without_secrets(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ENABLE_EXTERNAL_SOURCES", "true")
    monkeypatch.setenv("ENABLE_VENEZUELA_TE_BUSCA", "true")
    monkeypatch.setenv("VENEZUELA_TE_BUSCA_BASE_URL", "https://venezuelatebusca.com")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "super-secret-token")
    get_settings.cache_clear()

    record_failure("Venezuela Te Busca", "403 challenge", reason="cloudflare_challenge")
    payload = get_sources_health()
    text = str(payload)

    vtb = next(item for item in payload["sources"] if item["name"] == "Venezuela Te Busca")
    assert vtb["status"] == "degraded"
    assert vtb["reason"] == "cloudflare_challenge"
    assert vtb["degraded_until"] is not None
    assert "super-secret-token" not in text


def test_debug_shows_reason_and_degraded_until(client, db_session, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_SECRET", "debug-secret")
    monkeypatch.setenv("ENABLE_EXTERNAL_SOURCES", "true")
    monkeypatch.setenv("ENABLE_LOCALIZADOS_VENEZUELA", "true")
    get_settings.cache_clear()

    start = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
    with patch("app.sources.source_health_manager._utcnow", return_value=start):
        record_failure("Localizados Venezuela", "403", reason="cloudflare_challenge")

    with patch("app.sources.source_health_manager._utcnow", return_value=start + timedelta(minutes=1)):
        response = client.get(
            "/search",
            params={"q": "Juan Perez", "debug": "true", "secret": "debug-secret"},
        )

    assert response.status_code == 200
    provider = next(
        p for p in response.json()["debug"]["providers"] if p["name"] == "Localizados Venezuela"
    )
    assert provider["status"] == "degraded"
    assert provider["reason"] == "cloudflare_challenge"
    assert provider["degraded_until"] is not None


def test_record_failure_logs_degraded_message(caplog) -> None:
    fixed = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
    with caplog.at_level("WARNING"):
        with patch("app.sources.source_health_manager._utcnow", return_value=fixed):
            record_failure("Venezuela Te Busca", "403", reason="cloudflare_challenge")

    assert any("marcada como degraded" in record.message for record in caplog.records)


def test_should_skip_logs_skip_message(caplog) -> None:
    start = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
    with patch("app.sources.source_health_manager._utcnow", return_value=start):
        record_failure("Venezuela Te Busca", "403", reason="cloudflare_challenge")

    with caplog.at_level("INFO"):
        with patch("app.sources.source_health_manager._utcnow", return_value=start + timedelta(minutes=1)):
            should_skip("Venezuela Te Busca")

    assert any("Saltando Venezuela Te Busca" in record.message for record in caplog.records)
