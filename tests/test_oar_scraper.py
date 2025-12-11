from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.oar import OARScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed() -> BeautifulSoup:
    xml = (FIXTURES / "oar_feed.xml").read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = OARScraper()
    soup = load_feed()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert first.title == "Horari de l'OAR"
    assert (
        first.url
        == "https://ajuntament.barcelona.cat/oficina-afers-religiosos/ca/carrusel-promos-capcalera/promos/horari-de-loar"
    )
    assert "Horari de l'OAR" in first.summary
    assert first.published_at == datetime(2025, 12, 3, 13, 8, 4, tzinfo=timezone.utc)
    assert first.metadata["published_at"] == "2025-12-03T13:08:04+00:00"
