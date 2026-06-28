import json

from app.bot.response_format import (
    BOT_DISCLAIMER,
    BOT_MAX_SOURCE_LINKS,
    CARD_SEPARATOR,
    HIDDEN_RESULTS_MESSAGE,
    format_bot_match,
    format_search_response,
    needs_more_specific_query,
    result_display_limit,
    select_visible_matches,
)
from app.schemas.search import PersonMatch, SourceMatch


def _source(name: str, url: str = "https://example.com/x") -> SourceMatch:
    return SourceMatch(name=name, status="missing", source_url=url)


def _match(
    name: str,
    *,
    confidence: float = 80.0,
    status: str = "missing",
    source_count: int = 1,
    sources: list[SourceMatch] | None = None,
    status_conflict: bool = False,
    document_id_last4: str | None = None,
) -> PersonMatch:
    return PersonMatch(
        full_name=name,
        document_id_last4=document_id_last4,
        confidence_score=confidence,
        status=status,
        source_count=source_count,
        status_conflict=status_conflict,
        sources=sources or [_source("Fuente Test")],
    )


def test_disclaimer_appears_once_in_search_response() -> None:
    matches = [
        _match("Ana López", confidence=82.0),
        _match("Ana García", confidence=84.0),
    ]
    text = format_search_response(matches)
    assert text.count(BOT_DISCLAIMER) == 1
    assert "Información orientativa según fuentes públicas" in text


def test_disclaimer_not_repeated_inside_cards() -> None:
    text = format_bot_match(1, _match("Juan Pérez"))
    assert "Información orientativa" not in text
    assert "confirmación oficial" not in text


def test_low_confidence_shows_max_three_results() -> None:
    matches = [_match(f"Persona {index}", confidence=80.0 + index) for index in range(6)]
    visible, hidden = select_visible_matches(matches)

    assert result_display_limit(matches) == 3
    assert len(visible) == 3
    assert hidden == 3

    text = format_search_response(matches)
    assert text.count(CARD_SEPARATOR) == 3
    assert HIDDEN_RESULTS_MESSAGE in text


def test_high_confidence_shows_max_five_results() -> None:
    matches = [
        _match("Exacta", confidence=95.0),
        *[_match(f"Persona {index}", confidence=70.0 + index) for index in range(6)],
    ]
    visible, hidden = select_visible_matches(matches)

    assert result_display_limit(matches) == 5
    assert len(visible) == 5
    assert hidden == 2


def test_low_confidence_header_when_multiple_low_matches() -> None:
    matches = [_match("Ana Uno", confidence=82.0), _match("Ana Dos", confidence=85.0)]
    text = format_search_response(matches)

    assert needs_more_specific_query(matches) is True
    assert "🔎 Encontré varias coincidencias posibles" in text
    assert "• cédula" in text


def test_status_conflict_shown_in_card() -> None:
    text = format_bot_match(
        1,
        _match("Juan Pérez", status="found", status_conflict=True, confidence=95.0),
    )
    assert "estados diferentes" in text


def test_max_three_links_per_person() -> None:
    sources = [_source(f"Fuente {index}", f"https://example.com/{index}") for index in range(5)]
    match = _match(
        "Juan Pérez",
        confidence=95.0,
        source_count=len(sources),
        sources=sources,
    )

    text = format_bot_match(1, match)
    assert text.count("🔗 Fuente") == BOT_MAX_SOURCE_LINKS
    assert "https://example.com/4" not in text


def test_card_uses_status_emoji_and_spanish_labels() -> None:
    text = format_bot_match(1, _match("Juan Pérez", status="found", confidence=95.0))
    assert "🟢 Estado: Localizado/a" in text
    assert "missing" not in text
    assert "found" not in text


def test_card_does_not_expose_sensitive_fields() -> None:
    match = _match(
        "Juan Pérez",
        confidence=95.0,
        document_id_last4="5678",
        sources=[
            SourceMatch(
                name="Fuente Test",
                status="missing",
                source_url="https://example.com/x",
            )
        ],
    )
    text = format_bot_match(1, match)
    payload = json.dumps(match.model_dump(mode="json"))

    assert "5678" not in text
    assert "raw_data" not in text
    assert "5678" not in payload or "5678" not in text
    assert "1️⃣ Juan Pérez" in text
    assert "📊 Coincidencia: 95%" in text
