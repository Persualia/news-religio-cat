from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.caritasbarcelona import CaritasBarcelonaScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed() -> BeautifulSoup:
    xml = (FIXTURES / "caritasbarcelona_feed.xml").read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = CaritasBarcelonaScraper()
    soup = load_feed()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert first.title == "Voluntariado Corporativo: Pequeños gestos, grandes cambios"
    assert (
        first.url
        == "https://blog.caritas.barcelona/es/voluntariado/voluntariado-corporativo-pequenos-gestos-grandes-cambios"
    )
    assert "voluntariado corporativo" in first.summary.lower()
    assert first.published_at == datetime(2025, 12, 8, 8, 0, 56, tzinfo=timezone.utc)
    assert first.metadata["lang"] == "es"
