from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.caritasterrassa import CaritasTerrassaScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed() -> BeautifulSoup:
    xml = (FIXTURES / "caritasterrassa_feed.xml").read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = CaritasTerrassaScraper()
    soup = load_feed()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert first.title == "¡Hola mundo!"
    assert first.url == "https://diocesanaterrassa.caritas.es/es/hola-mundo"
    assert "Bienvenido a WordPress" in first.summary
    assert first.published_at == datetime(2017, 10, 19, 15, 15, 25, tzinfo=timezone.utc)
    assert first.metadata["lang"] == "es"
