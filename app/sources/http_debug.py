from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

FORBIDDEN_BODY_PREVIEW_CHARS = 500


def detect_block_reason(
    response: httpx.Response | None = None,
    *,
    exc: Exception | None = None,
) -> str | None:
    """Detecta motivo de bloqueo temporal (Cloudflare, rate limit, etc.)."""
    if exc is not None:
        if isinstance(exc, httpx.TimeoutException):
            return "timeout"
        if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
            response = exc.response

    if response is None:
        return None

    body = (response.text or "").lower()
    server = response.headers.get("server", "").lower()
    cf_mitigated = response.headers.get("cf-mitigated", "").lower()

    if "cloudflare" in server or cf_mitigated == "challenge":
        return "cloudflare_challenge"
    if "just a moment" in body or "challenges.cloudflare.com" in body:
        return "cloudflare_challenge"

    if response.status_code == 429:
        return "rate_limited"
    if response.status_code == 403:
        return "forbidden"

    return None


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
