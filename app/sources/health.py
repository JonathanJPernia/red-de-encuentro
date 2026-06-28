from app.config import get_settings
from app.services.status_labels import format_source_health_status_es
from app.sources.base_external_source import BaseExternalSource
from app.sources.desaparecidos_terremoto_venezuela_source import (
    DesaparecidosTerremotoVenezuelaSource,
)
from app.sources.emergencia_joch_source import EmergenciaJochSource
from app.sources.localizados_venezuela_source import LocalizadosVenezuelaSource
from app.sources.red_ayuda_venezuela_source import RedAyudaVenezuelaSource
from app.sources.registry import OPTIONAL_SOURCE_FLAGS
from app.sources.source_health_manager import get_status
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


def _config_status(settings, provider: BaseExternalSource, configured: bool) -> str:
    if not settings.enable_external_sources:
        return "disabled"

    for source_cls, flag_name in OPTIONAL_SOURCE_FLAGS.items():
        if isinstance(provider, source_cls) and not getattr(settings, flag_name):
            return "disabled"

    if not configured:
        return "not_configured"
    return "healthy"


def _merge_runtime_status(config_status: str, runtime: dict) -> str:
    if config_status in {"disabled", "not_configured"}:
        return config_status
    if runtime.get("status") == "degraded":
        return "degraded"
    return "healthy"


def get_sources_health() -> dict:
    settings = get_settings()
    items = []

    for source_cls in EXTERNAL_SOURCE_CLASSES:
        provider = source_cls()
        configured = provider.is_configured()
        enabled = _is_enabled(settings, provider)
        config_status = _config_status(settings, provider, configured)
        runtime = get_status(provider.source_name)
        status = _merge_runtime_status(config_status, runtime)

        item = {
            "name": provider.source_name,
            "enabled": enabled,
            "configured": configured,
            "status": status,
            "estado": format_source_health_status_es(status),
            "reason": runtime.get("reason") if status == "degraded" else None,
            "degraded_until": runtime.get("degraded_until") if status == "degraded" else None,
            "consecutive_failures": runtime.get("consecutive_failures", 0),
            "last_success_at": runtime.get("last_success_at"),
            "last_failure_at": runtime.get("last_failure_at"),
        }
        items.append(item)

    return {"sources": items}
