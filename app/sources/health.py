from app.config import get_settings
from app.sources.base_external_source import BaseExternalSource
from app.services.status_labels import format_source_health_status_es
from app.sources.desaparecidos_terremoto_venezuela_source import (
    DesaparecidosTerremotoVenezuelaSource,
)
from app.sources.emergencia_joch_source import EmergenciaJochSource
from app.sources.localizados_venezuela_source import LocalizadosVenezuelaSource
from app.sources.red_ayuda_venezuela_source import RedAyudaVenezuelaSource
from app.sources.registry import OPTIONAL_SOURCE_FLAGS
from app.sources.venezuela_te_busca_source import VenezuelaTeBuscaSource

EXTERNAL_SOURCE_CLASSES = [
    RedAyudaVenezuelaSource,
    EmergenciaJochSource,
    LocalizadosVenezuelaSource,
    DesaparecidosTerremotoVenezuelaSource,
    VenezuelaTeBuscaSource,
]


def _is_enabled(settings, provider: BaseExternalSource) -> bool:
    if not settings.enable_external_sources:
        return False

    for source_cls, flag_name in OPTIONAL_SOURCE_FLAGS.items():
        if isinstance(provider, source_cls):
            return bool(getattr(settings, flag_name)) and provider.is_configured()

    return provider.is_configured()


def _status_for_provider(settings, provider: BaseExternalSource, configured: bool) -> str:
    if not settings.enable_external_sources:
        return "disabled"

    for source_cls, flag_name in OPTIONAL_SOURCE_FLAGS.items():
        if isinstance(provider, source_cls) and not getattr(settings, flag_name):
            return "disabled"

    if not configured:
        return "not_configured"
    return "ready"


def get_sources_health() -> dict:
    settings = get_settings()
    items = []

    for source_cls in EXTERNAL_SOURCE_CLASSES:
        provider = source_cls()
        configured = provider.is_configured()
        enabled = _is_enabled(settings, provider)
        status = _status_for_provider(settings, provider, configured)

        items.append(
            {
                "name": provider.source_name,
                "enabled": enabled,
                "configured": configured,
                "status": status,
                "estado": format_source_health_status_es(status),
            }
        )

    return {"sources": items}
