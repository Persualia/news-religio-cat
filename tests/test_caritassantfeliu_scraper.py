from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.caritassantfeliu import CaritasSantFeliuScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed() -> BeautifulSoup:
    xml = (FIXTURES / "caritassantfeliu_feed.xml").read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = CaritasSantFeliuScraper()
    soup = load_feed()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert (
        first.title
        == "María González Dyne, nova secretària general de Càritas Espanyola"
    )
    assert (
        first.url
        == "https://www.caritassantfeliu.cat/maria-gonzalez-dyne-nova-secretaria-general-caritas-espanyola"
    )
    assert "Relleva Natalia Peiro" in first.summary
    assert first.published_at == datetime(2025, 12, 11, 8, 27, 5, tzinfo=timezone.utc)
    assert first.metadata["lang"] == "ca"
