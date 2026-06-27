"""Cliente reutilizable para APIs REST de Supabase."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SupabaseClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def get_table(
        self,
        table: str,
        *,
        select: str = "*",
        order: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        filters: dict[str, str] | None = None,
    ) -> tuple[list[dict[str, Any]], int | None]:
        params: dict[str, str] = {"select": select}
        if order:
            params["order"] = order
        if limit is not None:
            params["limit"] = str(limit)
        if offset:
            params["offset"] = str(offset)
        if filters:
            params.update(filters)

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/rest/v1/{table}",
                headers=self._headers(prefer="count=exact"),
                params=params,
            )
            response.raise_for_status()
            total = _parse_content_range(response.headers.get("content-range"))
            return response.json(), total

    def call_rpc(self, function: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/rest/v1/rpc/{function}",
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else []


def _parse_content_range(value: str | None) -> int | None:
    if not value or "/" not in value:
        return None
    try:
        return int(value.split("/")[-1])
    except ValueError:
        return None
