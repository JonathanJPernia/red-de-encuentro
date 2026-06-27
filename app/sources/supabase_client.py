from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0
MAX_RETRIES = 1
MIN_REQUEST_INTERVAL = 1.0


class SupabaseClient:
    """Cliente mínimo para APIs REST públicas de Supabase (solo anon key)."""

    _last_request_at: dict[str, float] = {}

    def __init__(
        self,
        base_url: str,
        anon_key: str,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.anon_key = anon_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.anon_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _rate_limit(self) -> None:
        now = time.monotonic()
        last = self._last_request_at.get(self.base_url, 0.0)
        elapsed = now - last
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_at[self.base_url] = time.monotonic()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            self._rate_limit()
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.request(method, url, headers=self._headers(), **kwargs)
                    response.raise_for_status()
                    return response
            except Exception as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "Reintento Supabase %s %s (intento %s): %s",
                        method,
                        path,
                        attempt + 1,
                        exc,
                    )
                    continue
                break

        assert last_error is not None
        raise last_error

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        response = self._request("GET", path, params=params)
        return response.json()

    def post(self, path: str, *, json: dict[str, Any] | None = None) -> Any:
        response = self._request("POST", path, json=json or {})
        return response.json()
