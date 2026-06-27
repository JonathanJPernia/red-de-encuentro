import json
import logging
from datetime import datetime

from app.config import get_settings
from app.scrapers.base_scraper import BaseScraper, ScrapedPerson
from app.scrapers.supabase_client import SupabaseClient
from app.services.normalize_service import extract_document_from_text, normalize_status

logger = logging.getLogger(__name__)

SOURCE_PAGE_URL = "https://redayudavenezuela.com/buscar"


class RedAyudaVenezuelaScraper(BaseScraper):
    """
    Sincroniza registros desde la API pública Supabase de Red Ayuda Venezuela.

    Estrategia: paginar la tabla `missing_persons` vía REST (no requiere Playwright).
    La UI en https://redayudavenezuela.com/buscar usa la RPC `search_people`, pero
    la tabla completa es accesible con la clave anon embebida en el frontend.
    """

    source_name = "Red Ayuda Venezuela"
    source_url = SOURCE_PAGE_URL
    reliability_level = 2

    def __init__(self) -> None:
        settings = get_settings()
        self.batch_size = settings.scraper_batch_size
        self.max_records = settings.redayuda_max_records
        self.client = SupabaseClient(
            base_url=settings.red_ayuda_supabase_url or settings.redayuda_supabase_url,
            api_key=settings.red_ayuda_supabase_anon_key or settings.redayuda_supabase_key,
        )

    def fetch(self) -> str:
        rows: list[dict] = []
        offset = 0
        total_available: int | None = None

        while len(rows) < self.max_records:
            batch_limit = min(self.batch_size, self.max_records - len(rows))
            try:
                batch, total_available = self.client.get_table(
                    "missing_persons",
                    select="id,ext_id,name,description,last_seen,status,source,synced_at,located_at,is_child",
                    order="synced_at.desc",
                    limit=batch_limit,
                    offset=offset,
                )
            except Exception:
                logger.exception(
                    "Red Ayuda Venezuela: fallo al descargar lote offset=%s", offset
                )
                raise

            if not batch:
                break

            rows.extend(batch)
            offset += len(batch)

            if total_available is not None:
                logger.info(
                    "Red Ayuda Venezuela: descargados %s/%s (lote %s)",
                    len(rows),
                    min(self.max_records, total_available),
                    len(batch),
                )

            if len(batch) < batch_limit:
                break

        return json.dumps(rows, ensure_ascii=False)

    def parse(self, raw_content: str) -> list[ScrapedPerson]:
        payload = json.loads(raw_content)
        records: list[ScrapedPerson] = []

        for item in payload:
            try:
                records.append(self._map_row(item))
            except Exception:
                logger.exception(
                    "Red Ayuda Venezuela: fila inválida ext_id=%s",
                    item.get("ext_id"),
                )
        return records

    def _map_row(self, item: dict) -> ScrapedPerson:
        full_name = (item.get("name") or "").strip()
        if not full_name:
            raise ValueError("Nombre vacío")

        description = item.get("description") or ""
        last_seen = item.get("last_seen") or ""
        document_id = extract_document_from_text(f"{full_name} {description} {last_seen}")

        if item.get("located_at"):
            status = "found"
        else:
            status = normalize_status(item.get("status") or "missing")
            if status == "unknown":
                status = "missing"

        synced_at = _parse_datetime(item.get("synced_at"))
        ext_id = item.get("ext_id") or item.get("id")
        source_url = f"{SOURCE_PAGE_URL}?ref={ext_id}"

        raw_data = {
            "ext_id": ext_id,
            "source_platform": item.get("source"),
            "description": description,
            "last_seen": last_seen,
            "is_child": item.get("is_child"),
            "located_at": item.get("located_at"),
        }

        return ScrapedPerson(
            full_name=full_name,
            document_id=document_id,
            status=status,
            source_url=source_url,
            published_at=synced_at,
            raw_data=raw_data,
        )


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
    if not settings.redayuda_supabase_key:
        raise SystemExit("REDAYUDA_SUPABASE_KEY no está configurado en .env")

    scraper = RedAyudaVenezuelaScraper()
    count = scraper.run()
    logger.info("Red Ayuda Venezuela: %s registros procesados", count)


if __name__ == "__main__":
    main()
