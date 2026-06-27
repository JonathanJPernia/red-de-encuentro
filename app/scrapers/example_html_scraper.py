"""Scraper de ejemplo que parsea HTML con BeautifulSoup."""

import logging
from pathlib import Path

from bs4 import BeautifulSoup

from app.scrapers.base_scraper import ScrapedPerson
from app.scrapers.http_scraper import HttpScraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_list.html"


class ExampleHtmlScraper(HttpScraper):
    source_name = "Ejemplo HTML"
    source_url = "https://example.com/lista-html"
    reliability_level = 1

    def target_url(self) -> str:
        return self.source_url

    def fetch(self) -> str:
        return FIXTURE_PATH.read_text(encoding="utf-8")

    def parse(self, raw_content: str) -> list[ScrapedPerson]:
        soup = BeautifulSoup(raw_content, "html.parser")
        records: list[ScrapedPerson] = []

        for row in soup.select("#missing-people tr"):
            name_el = row.select_one(".name")
            if not name_el:
                continue

            document_el = row.select_one(".document")
            status_el = row.select_one(".status")
            link_el = row.select_one(".link a")

            full_name = name_el.get_text(strip=True)
            source_url = link_el["href"] if link_el and link_el.has_attr("href") else self.source_url
            raw_data = {
                "full_name": full_name,
                "document_id": document_el.get_text(strip=True) if document_el else None,
                "status": status_el.get_text(strip=True) if status_el else "missing",
                "source_url": source_url,
            }

            records.append(
                ScrapedPerson(
                    full_name=full_name,
                    document_id=raw_data["document_id"],
                    status=raw_data["status"],
                    source_url=source_url,
                    raw_data=raw_data,
                )
            )

        return records


def main() -> None:
    scraper = ExampleHtmlScraper()
    count = scraper.run()
    logger.info("Insertados/actualizados %s registros", count)


if __name__ == "__main__":
    main()
