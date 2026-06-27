import json
from pathlib import Path

import pytest

from app.scrapers.emergencia_joch_scraper import EmergenciaJochScraper
from app.scrapers.redayudavenezuela_scraper import RedAyudaVenezuelaScraper
from app.services.normalize_service import sanitize_raw_data, split_name_and_document

FIXTURES = Path(__file__).parent.parent / "app" / "scrapers" / "fixtures"


def test_redayudavenezuela_parse_fixture() -> None:
    scraper = RedAyudaVenezuelaScraper.__new__(RedAyudaVenezuelaScraper)
    raw = (FIXTURES / "redayudavenezuela_sample.json").read_text(encoding="utf-8")
    records = scraper.parse(raw)

    assert len(records) == 1
    assert records[0].full_name == "Bryana Rodríguez"
    assert records[0].status == "missing"
    assert "redayudavenezuela.com/buscar" in (records[0].source_url or "")
    assert sanitize_raw_data(records[0].raw_data) is not None
    assert "document_id" not in (records[0].raw_data or {})


def test_emergencia_joch_parse_fixture() -> None:
    scraper = EmergenciaJochScraper.__new__(EmergenciaJochScraper)
    raw = (FIXTURES / "emergencia_joch_sample.json").read_text(encoding="utf-8")
    records = scraper.parse(raw)

    assert len(records) == 1
    assert records[0].full_name == "Francys Arocha"
    assert records[0].document_id == "11144145"
    assert records[0].status == "missing"

    sanitized = sanitize_raw_data(
        {
            "report_id": 2,
            "detalles_emergencia": "CI: V-11.144.145 en edificio",
        }
    )
    assert sanitized is not None
    assert sanitized["document_id_last4"] == "4145"
    assert "11144145" not in json.dumps(sanitized)


def test_split_name_and_document() -> None:
    name, doc = split_name_and_document("jose (CI: V-20890738)")
    assert name == "jose"
    assert doc == "20890738"
