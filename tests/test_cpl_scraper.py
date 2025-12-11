from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.cpl import CPLScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed() -> BeautifulSoup:
    xml = (FIXTURES / "cpl_feed.xml").read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = CPLScraper()
    soup = load_feed()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert first.title == "Webinar CPL: presentación de «Mujeres diáconos: debate contemporáneo»"
    assert (
        first.url
        == "https://www.cpl.es/webinar-cpl-presentacion-de-mujeres-diaconos-debate-contemporaneo"
    )
    assert "Cuadernos Phase" in first.summary
    assert first.published_at == datetime(2025, 10, 16, 7, 34, 30, tzinfo=timezone.utc)
    assert first.metadata["lang"] == "es"
