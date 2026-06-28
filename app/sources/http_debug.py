from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

FORBIDDEN_BODY_PREVIEW_CHARS = 500


def log_forbidden_response(
    source_name: str,
    response: httpx.Response,
    *,
    url: str | None = None,
) -> None:
    """Registra detalle de un 403 para diagnosticar Cloudflare, WAF, etc."""
    if response.status_code != 403:
        return

    request_url = url or str(response.request.url)
    body_preview = (response.text or "")[:FORBIDDEN_BODY_PREVIEW_CHARS]
    header_lines = "\n".join(f"    {key}: {value}" for key, value in response.headers.items())

    logger.warning(
        "HTTP 403 en %s\n"
        "  url: %s\n"
        "  status: %s\n"
        "  headers:\n%s\n"
        "  body (primeros %s chars):\n%s",
        source_name,
        request_url,
        response.status_code,
        header_lines or "    (vacío)",
        FORBIDDEN_BODY_PREVIEW_CHARS,
        body_preview or "(vacío)",
    )


def raise_for_status_logged(source_name: str, response: httpx.Response) -> None:
    """Loguea 403 con detalle y luego delega en raise_for_status."""
    log_forbidden_response(source_name, response)
    response.raise_for_status()
