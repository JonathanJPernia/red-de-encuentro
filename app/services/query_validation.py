import re

from app.services.normalize_service import is_document_query, normalize_document_id, normalize_name

GENERIC_QUERIES = frozenset(
    {
        "a",
        "de",
        "del",
        "el",
        "la",
        "lo",
        "y",
        "en",
        "un",
        "una",
    }
)

MIN_NAME_LENGTH = 3
MIN_DOCUMENT_DIGITS = 5


def validate_search_query(query: str) -> str:
    """Valida consultas de búsqueda antes de consultar DB o fuentes externas."""
    stripped = query.strip()
    if not stripped:
        raise ValueError("La consulta no puede estar vacía")

    if is_document_query(stripped):
        digits = normalize_document_id(stripped)
        if len(digits) < MIN_DOCUMENT_DIGITS:
            raise ValueError("La cédula debe tener al menos 5 dígitos")
        return stripped

    normalized = normalize_name(stripped)
    if normalized in GENERIC_QUERIES:
        raise ValueError("Consulta demasiado genérica. Usa un nombre más específico")
    if len(normalized) < MIN_NAME_LENGTH:
        raise ValueError("El nombre debe tener al menos 3 caracteres")
    if re.fullmatch(r"[a-z0-9]", normalized):
        raise ValueError("Consulta demasiado genérica. Usa un nombre más específico")

    return stripped
