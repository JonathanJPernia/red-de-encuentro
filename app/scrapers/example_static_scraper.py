"""Scraper de ejemplo con datos estáticos para pruebas locales."""

import json
import logging

from app.scrapers.base_scraper import BaseScraper, ScrapedPerson

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SAMPLE_DATA = [
    {
        "full_name": "Juan Carlos Pérez",
        "document_id": "12345678",
        "status": "missing",
        "source_url": "https://example.com/lista",
    }
]


class ExampleStaticScraper(BaseScraper):
    source_name = "Ejemplo estático"
    source_url = "https://example.com/lista"
    reliability_level = 1

    def fetch(self) -> str:
        return json.dumps(SAMPLE_DATA)

    def parse(self, raw_content: str) -> list[ScrapedPerson]:
        payload = json.loads(raw_content)
        return [
            ScrapedPerson(
                full_name=item["full_name"],
                document_id=item.get("document_id"),
                status=item.get("status", "missing"),
                source_url=item.get("source_url"),
                raw_data=item,
            )
            for item in payload
        ]


def main() -> None:
    scraper = ExampleStaticScraper()
    count = scraper.run()
    logger.info("Insertados/actualizados %s registros", count)


if __name__ == "__main__":
    main()
