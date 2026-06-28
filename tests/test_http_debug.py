import httpx

from app.sources.http_debug import (
    FORBIDDEN_BODY_PREVIEW_CHARS,
    detect_block_reason,
    log_forbidden_response,
    raise_for_status_logged,
)


def test_detect_block_reason_cloudflare_from_response() -> None:
    request = httpx.Request("GET", "https://example.com/")
    response = httpx.Response(
        403,
        headers={"server": "cloudflare", "cf-mitigated": "challenge"},
        text="Just a moment...",
        request=request,
    )
    assert detect_block_reason(response=response) == "cloudflare_challenge"


def test_log_forbidden_response_includes_status_headers_and_body(caplog) -> None:
    request = httpx.Request("GET", "https://example.com/api/personas?q=test")
    body = "Cloudflare\nAttention Required\n" + ("x" * 600)
    response = httpx.Response(
        403,
        headers={
            "server": "cloudflare",
            "cf-ray": "abc123",
            "content-type": "text/html",
        },
        text=body,
        request=request,
    )

    with caplog.at_level("WARNING"):
        log_forbidden_response("Desaparecidos Terremoto Venezuela", response)

    assert len(caplog.records) == 1
    message = caplog.records[0].message
    assert "403" in message
    assert "https://example.com/api/personas?q=test" in message
    assert "server: cloudflare" in message
    assert "cf-ray: abc123" in message
    assert "Cloudflare" in message
    assert "Attention Required" in message
    assert "x" * 501 not in message
    assert "x" * 500 in message or body[:500] in message


def test_log_forbidden_response_ignores_non_403(caplog) -> None:
    request = httpx.Request("GET", "https://example.com/")
    response = httpx.Response(200, text="ok", request=request)

    with caplog.at_level("WARNING"):
        log_forbidden_response("Test", response)

    assert caplog.records == []


def test_raise_for_status_logged_logs_before_raising(caplog) -> None:
    request = httpx.Request("GET", "https://example.com/")
    response = httpx.Response(403, text="Forbidden", request=request)

    with caplog.at_level("WARNING"):
        try:
            raise_for_status_logged("Localizados Venezuela", response)
        except httpx.HTTPStatusError:
            pass

    assert any("403" in record.message for record in caplog.records)
