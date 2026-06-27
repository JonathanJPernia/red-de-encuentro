from datetime import datetime

from app.schemas.search import PersonMatch
from app.services.status_labels import INFORMATIONAL_DISCLAIMER_SHORT, format_status_es

LOW_CONFIDENCE_THRESHOLD = 90.0
BOT_MAX_SOURCE_LINKS = 3
STATUS_CONFLICT_MESSAGE = (
    "⚠️ Hay fuentes con estados diferentes. Revisa los enlaces originales."
)


def needs_more_specific_query(matches: list[PersonMatch]) -> bool:
    """True si hay varias coincidencias posibles con baja confianza."""
    if len(matches) < 2:
        return False
    low_confidence = [match for match in matches if match.confidence_score < LOW_CONFIDENCE_THRESHOLD]
    return len(low_confidence) >= 2


def format_bot_match(index: int, match: PersonMatch) -> str:
    """Formatea un resultado consolidado para Telegram sin datos internos."""
    lines = [
        f"{index}. Nombre: {match.full_name}",
        f"Estado: {format_status_es(match.status)}",
        f"Coincidencia: {match.confidence_score:.0f}%",
        f"Fuentes encontradas: {match.source_count}",
        INFORMATIONAL_DISCLAIMER_SHORT,
    ]

    if match.status_conflict:
        lines.append(STATUS_CONFLICT_MESSAGE)

    links_shown = 0
    for source in match.sources:
        if not source.source_url:
            continue
        if links_shown >= BOT_MAX_SOURCE_LINKS:
            break
        lines.append(f"Enlace ({source.name}): {source.source_url}")
        links_shown += 1

    if links_shown == 0:
        lines.append("Enlace: no disponible")

    return "\n".join(lines)


def _format_date(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m-%d")
