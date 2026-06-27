from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.database_url import normalize_database_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = (
        "postgresql+psycopg2://bot_tl:bot_tl_dev@localhost:5435/missing_people_bot"
    )
    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = False
    telegram_bot_token: str = ""

    enable_external_sources: bool = False
    enable_red_ayuda_venezuela: bool = True
    enable_emergencia_joch: bool = True
    red_ayuda_supabase_url: str = "https://cpavwkdonvkvrwygfzfo.supabase.co"
    red_ayuda_supabase_anon_key: str = ""
    emergencia_joch_supabase_url: str = "https://pczsfbreefbtogmzigjw.supabase.co"
    emergencia_joch_supabase_anon_key: str = ""

    enable_localizados_venezuela: bool = False
    localizados_venezuela_base_url: str = "https://localizadosvenezuela.com"

    enable_desaparecidos_terremoto_venezuela: bool = False
    desaparecidos_terremoto_base_url: str = "https://desaparecidos-terremoto-api.theempire.tech"
    desaparecidos_terremoto_public_url: str = "https://desaparecidosterremotovenezuela.com"

    enable_venezuela_te_busca: bool = False
    venezuela_te_busca_base_url: str = "https://venezuelatebusca.com"

    # Compatibilidad con scrapers legacy (Fase 7 anterior)
    scraper_batch_size: int = 500
    redayuda_supabase_url: str = ""
    redayuda_supabase_key: str = ""
    redayuda_max_records: int = 500
    emergencia_joch_supabase_key: str = ""

    @model_validator(mode="after")
    def _apply_legacy_env_aliases(self) -> "Settings":
        self.database_url = normalize_database_url(self.database_url)

        if not self.red_ayuda_supabase_anon_key and self.redayuda_supabase_key:
            self.red_ayuda_supabase_anon_key = self.redayuda_supabase_key
        if self.redayuda_supabase_url:
            self.red_ayuda_supabase_url = self.redayuda_supabase_url
        if not self.emergencia_joch_supabase_anon_key and self.emergencia_joch_supabase_key:
            self.emergencia_joch_supabase_anon_key = self.emergencia_joch_supabase_key
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
