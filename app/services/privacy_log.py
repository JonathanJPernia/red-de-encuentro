from app.services.normalize_service import is_document_query, normalize_document_id


def mask_query_for_log(query: str) -> str:
    """Enmascara consultas que parecen cédula para logs."""
    stripped = query.strip()
    if not stripped:
        return ""

    if is_document_query(stripped):
        digits = normalize_document_id(stripped)
        if len(digits) >= 4:
            return f"***{digits[-4:]}"
        return "***"

    return stripped
