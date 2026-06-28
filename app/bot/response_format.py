from datetime import datetime

from app.schemas.search import PersonMatch, SourceMatch
from app.services.normalize_service import normalize_status

LOW_CONFIDENCE_THRESHOLD = 90.0
BOT_MAX_SOURCE_LINKS = 3
BOT_MAX_RESULTS_LOW_CONFIDENCE = 3
BOT_MAX_RESULTS_HIGH_CONFIDENCE = 5

CARD_SEPARATOR = "━━━━━━━━━━━━━━"
INDEX_EMOJIS = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟")

STATUS_EMOJI = {
    "found": "🟢",
    "missing": "🟠",
    "hospital": "🏥",
    "shelter": "🏠",
    "unknown": "⚪",
}

STATUS_CARD_LABELS = {
    "found": "Localizado/a",
    "missing": "Desaparecido/a",
    "hospital": "En hospital",
    "shelter": "En refugio",
    "unknown": "No confirmado",
}

LOW_CONFIDENCE_HEADER = (
    "🔎 Encontré varias coincidencias posibles\n\n"
    "Para mejorar la búsqueda, intenta con:\n"
    "• nombre completo\n"
    "• cédula\n"
    "• dos apellidos"
)

STATUS_CONFLICT_MESSAGE = (
    "⚠️ Hay fuentes con estados diferentes. Revisa los enlaces originales."
)

HIDDEN_RESULTS_MESSAGE = (
    "Hay más coincidencias posibles. Intenta con cédula o apellido adicional."
)

BOT_DISCLAIMER = (
    "⚠️ Información orientativa según fuentes públicas.\n"
    "No sustituye confirmación oficial.\n"
    "Verifica siempre en el enlace original."
)


def needs_more_specific_query(matches: list[PersonMatch]) -> bool:
    """True si hay varias coincidencias posibles con baja confianza."""
    if len(matches) < 2:
        return False
    low_confidence = [match for match in matches if match.confidence_score < LOW_CONFIDENCE_THRESHOLD]
    return len(low_confidence) >= 2


def result_display_limit(matches: list[PersonMatch]) -> int:
    if any(match.confidence_score >= LOW_CONFIDENCE_THRESHOLD for match in matches):
        return BOT_MAX_RESULTS_HIGH_CONFIDENCE
    return BOT_MAX_RESULTS_LOW_CONFIDENCE


def select_visible_matches(matches: list[PersonMatch]) -> tuple[list[PersonMatch], int]:
    limit = result_display_limit(matches)
    visible = matches[:limit]
    hidden_count = max(len(matches) - len(visible), 0)
    return visible, hidden_count


def _format_index(index: int) -> str:
    if 1 <= index <= len(INDEX_EMOJIS):
        return INDEX_EMOJIS[index - 1]
    return f"{index}."


def _format_status_line(match: PersonMatch) -> str:
    status_key = normalize_status(match.status)
    emoji = STATUS_EMOJI.get(status_key, STATUS_EMOJI["unknown"])
    label = STATUS_CARD_LABELS.get(status_key, STATUS_CARD_LABELS["unknown"])
    return f"{emoji} Estado: {label}"


def format_bot_match(index: int, match: PersonMatch) -> str:
    """Formatea una tarjeta compacta para Telegram sin datos sensibles."""
    lines = [
        CARD_SEPARATOR,
        f"{_format_index(index)} {match.full_name}",
        "",
        _format_status_line(match),
        f"📊 Coincidencia: {match.confidence_score:.0f}%",
        f"📚 Fuentes: {match.source_count}",
    ]

    if match.status_conflict:
        lines.append(STATUS_CONFLICT_MESSAGE)

    links_shown = 0
    for source in match.sources:
        if not source.source_url:
            continue
        if links_shown >= BOT_MAX_SOURCE_LINKS:
            break
        lines.extend([f"🔗 {source.name}", source.source_url])
        links_shown += 1

    if links_shown == 0:
        lines.append("🔗 Enlace no disponible")

    return "\n".join(lines)


def format_search_response(matches: list[PersonMatch]) -> str:
    visible_matches, hidden_count = select_visible_matches(matches)
    blocks: list[str] = []

    if needs_more_specific_query(matches):
        blocks.extend([LOW_CONFIDENCE_HEADER, ""])

    for index, match in enumerate(visible_matches, start=1):
        blocks.append(format_bot_match(index, match))
        blocks.append("")

    if hidden_count > 0:
        blocks.extend([HIDDEN_RESULTS_MESSAGE, ""])

    blocks.append(BOT_DISCLAIMER)
    return "\n".join(blocks).strip()


def _format_date(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m-%d")
