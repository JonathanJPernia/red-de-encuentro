"""Ejecuta todos los scrapers registrados."""

import logging
import sys

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.example_html_scraper import ExampleHtmlScraper
from app.scrapers.example_static_scraper import ExampleStaticScraper

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SCRAPERS: list[type[BaseScraper]] = [
    ExampleStaticScraper,
    ExampleHtmlScraper,
]


def run_all() -> dict[str, int]:
    results: dict[str, int] = {}
    for scraper_cls in SCRAPERS:
        scraper = scraper_cls()
        logger.info("Ejecutando scraper: %s", scraper.source_name)
        try:
            results[scraper.source_name] = scraper.run()
        except Exception:
            logger.exception("Error en scraper %s", scraper.source_name)
            results[scraper.source_name] = -1
    return results


def main() -> None:
    results = run_all()
    failed = [name for name, count in results.items() if count < 0]
    total = sum(count for count in results.values() if count >= 0)

    for name, count in results.items():
        status = "OK" if count >= 0 else "ERROR"
        logger.info("[%s] %s: %s registros", status, name, count)

    logger.info("Total procesado: %s registros", total)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
