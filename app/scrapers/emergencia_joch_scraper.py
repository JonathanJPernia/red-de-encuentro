import json
import logging
from datetime import datetime

from app.config import get_settings
from app.scrapers.base_scraper import BaseScraper, ScrapedPerson
from app.scrapers.supabase_client import SupabaseClient
from app.services.normalize_service import (
    normalize_status,
    split_name_and_document,
)

logger = logging.getLogger(__name__)

SOURCE_PAGE_URL = "https://emergencia.joch.dev/"

STATUS_MAP = {
    "desaparecido": "missing",
    "desaparecida": "missing",
    "a salvo": "found",
    "salvo": "found",
    "encontrado": "found",
    "encontrada": "found",
    "hospital": "hospital",
    "hospitalizado": "hospital",
    "hospitalizada": "hospital",
    "refugio": "shelter",
    "albergue": "shelter",
    "atrapado / herido": "hospital",
    "herido": "hospital",
}


class EmergenciaJochScraper(BaseScraper):
    """
    Sincroniza reportes desde la API Supabase de emergencia.joch.dev.

    Estrategia: GET directo a `reportes_emergencias` con clave publishable del frontend.
    """

    source_name = "Emergencia Joch.dev"
    source_url = SOURCE_PAGE_URL
    reliability_level = 2

    def __init__(self) -> None:
        settings = get_settings()
        self.client = SupabaseClient(
            base_url=settings.emergencia_joch_supabase_url,
            api_key=settings.emergencia_joch_supabase_key,
        )

    def fetch(self) -> str:
        try:
            rows, total = self.client.get_table(
                "reportes_emergencias",
                select=(
                    "id,nombre_completo,estado_persona,detalles_emergencia,"
                    "created_at,direccion_exacta,estado_id,municipio_id"
                ),
                order="created_at.desc",
                limit=1000,
            )
            logger.info(
                "Emergencia Joch.dev: descargados %s registros (total remoto ~%s)",
                len(rows),
                total,
            )
            return json.dumps(rows, ensure_ascii=False)
        except Exception:
            logger.exception("Emergencia Joch.dev: fallo al descargar reportes")
            raise

    def parse(self, raw_content: str) -> list[ScrapedPerson]:
        payload = json.loads(raw_content)
        records: list[ScrapedPerson] = []

        for item in payload:
            try:
                records.append(self._map_row(item))
            except Exception:
                logger.exception(
                    "Emergencia Joch.dev: fila inválida id=%s",
                    item.get("id"),
                )
        return records

    def _map_row(self, item: dict) -> ScrapedPerson:
        raw_name = (item.get("nombre_completo") or "").strip()
        if not raw_name:
            raise ValueError("Nombre vacío")

        full_name, document_id = split_name_and_document(raw_name)
        if not document_id:
            document_id = split_name_and_document(item.get("detalles_emergencia") or "")[1]

        status = _map_status(item.get("estado_persona") or "unknown")
        report_id = item.get("id")
        source_url = f"{SOURCE_PAGE_URL}#reporte-{report_id}"
        published_at = _parse_datetime(item.get("created_at"))

        raw_data = {
            "report_id": report_id,
            "estado_persona": item.get("estado_persona"),
            "detalles_emergencia": item.get("detalles_emergencia"),
            "direccion_exacta": item.get("direccion_exacta"),
            "estado_id": item.get("estado_id"),
            "municipio_id": item.get("municipio_id"),
        }

        return ScrapedPerson(
            full_name=full_name,
            document_id=document_id,
            status=status,
            source_url=source_url,
            published_at=published_at,
            raw_data=raw_data,
        )


def _map_status(raw_status: str) -> str:
    key = raw_status.strip().lower()
    mapped = STATUS_MAP.get(key)
    if mapped:
        return mapped
    return normalize_status(raw_status)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.emergencia_joch_supabase_key:
        raise SystemExit("EMERGENCIA_JOCH_SUPABASE_KEY no está configurado en .env")

    scraper = EmergenciaJochScraper()
    count = scraper.run()
    logger.info("Emergencia Joch.dev: %s registros procesados", count)


if __name__ == "__main__":
    main()
