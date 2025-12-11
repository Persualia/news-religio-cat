from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.adoratrius import AdoratriusScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed() -> BeautifulSoup:
    xml = (FIXTURES / "adoratrius_feed.xml").read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = AdoratriusScraper()
    soup = load_feed()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert first.title == "Sicar cat se integra a Fundación Amaranta"
    assert first.url == "https://adoratrius.cat/sicar-cat-se-integra-a-fundacion-amaranta"
    assert "SICAR cat" in first.summary
    assert first.published_at == datetime(2024, 1, 2, 13, 13, 39, tzinfo=timezone.utc)
