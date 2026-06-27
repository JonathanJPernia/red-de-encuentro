from app.services.normalize_service import normalize_status

STATUS_LABELS_ES = {
    "missing": "Desaparecido/a (según fuente)",
    "found": "Localizado/a (según fuente)",
    "hospital": "Reportado en hospital (según fuente)",
    "shelter": "Reportado en refugio (según fuente)",
    "unknown": "Estado no confirmado",
}

SOURCE_HEALTH_LABELS_ES = {
    "disabled": "Desactivada",
    "not_configured": "Sin configurar",
    "ready": "Operativa",
}

INFORMATIONAL_DISCLAIMER = (
    "Aviso informativo: los resultados provienen de fuentes públicas y son solo orientativos. "
    "No sustituyen información oficial ni confirmación de las autoridades. "
    "Pueden existir errores, retrasos o estados distintos entre fuentes. "
    "Verifica siempre en el enlace original antes de actuar."
)

INFORMATIONAL_DISCLAIMER_SHORT = (
    "ℹ️ Información orientativa según fuentes públicas; no es confirmación oficial."
)


def format_status_es(status: str) -> str:
    normalized = normalize_status(status)
    return STATUS_LABELS_ES.get(normalized, STATUS_LABELS_ES["unknown"])


def format_source_health_status_es(status: str) -> str:
    return SOURCE_HEALTH_LABELS_ES.get(status, status)
