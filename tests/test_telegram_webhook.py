from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_telegram_webhook_returns_ok(client) -> None:
    with patch(
        "app.main.process_telegram_update",
        new=AsyncMock(),
    ) as mock_process:
        response = client.post(
            "/telegram/webhook",
            json={"update_id": 1, "message": {"message_id": 1, "chat": {"id": 1}, "text": "hola"}},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    mock_process.assert_awaited_once()


def test_telegram_webhook_does_not_crash_api_on_failure(client) -> None:
    with patch(
        "app.main.process_telegram_update",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        response = client.post("/telegram/webhook", json={"update_id": 2})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_telegram_status_does_not_expose_token(client, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "super-secret-token")
    get_settings.cache_clear()

    response = client.get("/telegram/status")
    payload = response.json()

    assert response.status_code == 200
    assert payload == {"mode": "webhook", "configured": True}
    assert "super-secret-token" not in str(payload)


def test_admin_set_webhook_requires_secret(client, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_SECRET", "test-admin-secret")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://red-de-encuentro-api.onrender.com")
    get_settings.cache_clear()

    with patch("app.main.set_webhook", return_value={"ok": True, "result": True}) as mock_set:
        response = client.post(
            "/admin/telegram/set-webhook",
            headers={"X-Admin-Secret": "wrong-secret"},
            json={},
        )

    assert response.status_code == 403
    mock_set.assert_not_called()


def test_admin_set_webhook_works_with_valid_secret(client, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_SECRET", "test-admin-secret")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://red-de-encuentro-api.onrender.com")
    get_settings.cache_clear()

    with patch("app.main.set_webhook", return_value={"ok": True, "result": True}) as mock_set:
        response = client.post(
            "/admin/telegram/set-webhook",
            headers={"X-Admin-Secret": "test-admin-secret"},
            json={},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["webhook_url"] == "https://red-de-encuentro-api.onrender.com/telegram/webhook"
    mock_set.assert_called_once_with("https://red-de-encuentro-api.onrender.com/telegram/webhook")


def test_admin_endpoints_hidden_without_admin_secret(client, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.delenv("ADMIN_SECRET", raising=False)
    get_settings.cache_clear()

    response = client.post(
        "/admin/telegram/set-webhook",
        headers={"X-Admin-Secret": "anything"},
        json={},
    )
    assert response.status_code == 404

    response = client.post(
        "/admin/telegram/delete-webhook",
        headers={"X-Admin-Secret": "anything"},
    )
    assert response.status_code == 404
