import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.main import app
from app.models.search_log import SearchLog
from app.services.analytics_service import (
    get_admin_stats,
    hash_user_identifier,
    log_search,
    prepare_query_analytics,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_prepare_query_analytics_masks_document() -> None:
    masked, query_hash = prepare_query_analytics("V-12345678")
    assert masked == "***5678"
    assert "12345678" not in masked
    assert query_hash == hashlib.sha256(masked.encode("utf-8")).hexdigest()


def test_prepare_query_analytics_normalizes_name() -> None:
    masked, _ = prepare_query_analytics("María Pérez")
    assert masked == "maria perez"


def test_hash_user_identifier_does_not_store_raw_id() -> None:
    user_hash = hash_user_identifier("telegram", "987654321")
    assert user_hash is not None
    assert "987654321" not in user_hash
    assert user_hash == hash_user_identifier("telegram", "987654321")


def test_log_search_persists_masked_fields(db_session) -> None:
    log_search(
        db_session,
        source="api",
        query="12345678",
        results_count=2,
        response_ms=120,
        success=True,
        user_identifier="203.0.113.10",
    )

    entry = db_session.scalars(select(SearchLog).order_by(SearchLog.id.desc())).first()
    assert entry is not None
    assert entry.source == "api"
    assert entry.query_masked == "***5678"
    assert "12345678" not in entry.query_masked
    assert entry.user_hash != "203.0.113.10"
    assert "203.0.113.10" not in (entry.user_hash or "")

    db_session.delete(entry)
    db_session.commit()


def test_log_search_telegram_source(db_session) -> None:
    log_search(
        db_session,
        source="telegram",
        query="Juan Perez",
        results_count=0,
        response_ms=80,
        success=True,
        user_identifier="555001",
    )
    entry = db_session.scalars(select(SearchLog).order_by(SearchLog.id.desc())).first()
    assert entry.source == "telegram"
    assert entry.query_masked == "juan perez"
    assert "555001" not in (entry.user_hash or "")

    db_session.delete(entry)
    db_session.commit()


def test_get_admin_stats_summary(db_session) -> None:
    log_search(
        db_session,
        source="telegram",
        query="maria perez",
        results_count=1,
        response_ms=100,
        success=True,
        user_identifier="user-a",
    )
    log_search(
        db_session,
        source="api",
        query="12345678",
        results_count=0,
        response_ms=200,
        success=True,
        user_identifier="1.2.3.4",
    )

    stats = get_admin_stats(db_session, days=7)
    assert stats["total_searches"] >= 2
    assert stats["telegram_searches"] >= 1
    assert stats["api_searches"] >= 1
    assert stats["unique_users"] >= 2
    assert any(item["query"] == "maria perez" for item in stats["top_queries"])

    entries = db_session.scalars(select(SearchLog).order_by(SearchLog.id.desc()).limit(2)).all()
    for entry in entries:
        db_session.delete(entry)
    db_session.commit()


def test_admin_stats_without_secret_returns_404(client, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.delenv("ADMIN_SECRET", raising=False)
    get_settings.cache_clear()

    response = client.get("/admin/stats?days=7")
    assert response.status_code == 404


def test_admin_stats_with_wrong_secret_returns_403(client, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_SECRET", "correct-secret")
    get_settings.cache_clear()

    response = client.get(
        "/admin/stats?days=7",
        headers={"X-Admin-Secret": "wrong-secret"},
    )
    assert response.status_code == 403


def test_admin_stats_with_valid_secret_returns_stats(client, db_session, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_SECRET", "stats-secret")
    get_settings.cache_clear()

    log_search(
        db_session,
        source="api",
        query="maria perez",
        results_count=3,
        response_ms=150,
        success=True,
        user_identifier="10.0.0.1",
    )

    response = client.get(
        "/admin/stats?days=7",
        headers={"X-Admin-Secret": "stats-secret"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["period_days"] == 7
    assert payload["total_searches"] >= 1
    assert "12345678" not in str(payload)
    assert "10.0.0.1" not in str(payload)
    assert "stats-secret" not in str(payload)

    entry = db_session.scalars(select(SearchLog).order_by(SearchLog.id.desc())).first()
    if entry is not None:
        db_session.delete(entry)
        db_session.commit()


def test_admin_dashboard_without_secret_returns_403(client, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_SECRET", "dash-secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "super-secret-token")
    get_settings.cache_clear()

    response = client.get("/admin/dashboard")
    assert response.status_code == 403


def test_admin_dashboard_without_admin_secret_configured_returns_404(client, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.delenv("ADMIN_SECRET", raising=False)
    get_settings.cache_clear()

    response = client.get("/admin/dashboard?secret=anything")
    assert response.status_code == 404


def test_admin_dashboard_with_secret_returns_html(client, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_SECRET", "dash-secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "super-secret-token")
    get_settings.cache_clear()

    response = client.get("/admin/dashboard?secret=dash-secret")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Red de Encuentro — Analytics" in response.text
    assert "Panel privado" in response.text
    assert "super-secret-token" not in response.text
    assert "dash-secret" not in response.text


def test_admin_dashboard_data_with_secret_returns_json(client, db_session, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_SECRET", "dash-secret")
    get_settings.cache_clear()

    log_search(
        db_session,
        source="telegram",
        query="maria perez",
        results_count=1,
        response_ms=90,
        success=True,
        user_identifier="tg-user",
    )
    log_search(
        db_session,
        source="api",
        query="12345678",
        results_count=0,
        response_ms=120,
        success=False,
        error_type="validation_error",
        user_identifier="1.2.3.4",
    )

    response = client.get("/admin/dashboard-data?days=7&secret=dash-secret")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_searches"] >= 2
    assert any(item["query"] == "maria perez" for item in payload["top_queries"])
    assert any(item["query"] == "***5678" for item in payload["top_queries"])
    assert "12345678" not in str(payload)
    assert payload["recent_errors"]

    entries = db_session.scalars(select(SearchLog).order_by(SearchLog.id.desc()).limit(2)).all()
    for entry in entries:
        db_session.delete(entry)
    db_session.commit()
