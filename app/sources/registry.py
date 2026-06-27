from app.config import get_settings
from app.sources.base_external_source import BaseExternalSource
from app.sources.desaparecidos_terremoto_venezuela_source import (
    DesaparecidosTerremotoVenezuelaSource,
)
from app.sources.emergencia_joch_source import EmergenciaJochSource
from app.sources.localizados_venezuela_source import LocalizadosVenezuelaSource
from app.sources.red_ayuda_venezuela_source import RedAyudaVenezuelaSource
from app.sources.venezuela_te_busca_source import VenezuelaTeBuscaSource

OPTIONAL_SOURCE_FLAGS: dict[type[BaseExternalSource], str] = {
    RedAyudaVenezuelaSource: "enable_red_ayuda_venezuela",
    EmergenciaJochSource: "enable_emergencia_joch",
    LocalizadosVenezuelaSource: "enable_localizados_venezuela",
    DesaparecidosTerremotoVenezuelaSource: "enable_desaparecidos_terremoto_venezuela",
    VenezuelaTeBuscaSource: "enable_venezuela_te_busca",
}


def get_external_sources() -> list[BaseExternalSource]:
    settings = get_settings()
    if not settings.enable_external_sources:
        return []

    providers: list[BaseExternalSource] = []

    if settings.enable_red_ayuda_venezuela:
        providers.append(RedAyudaVenezuelaSource())

    if settings.enable_emergencia_joch:
        providers.append(EmergenciaJochSource())

    if settings.enable_localizados_venezuela:
        providers.append(LocalizadosVenezuelaSource())

    if settings.enable_desaparecidos_terremoto_venezuela:
        providers.append(DesaparecidosTerremotoVenezuelaSource())

    if settings.enable_venezuela_te_busca:
        providers.append(VenezuelaTeBuscaSource())

    return providers
