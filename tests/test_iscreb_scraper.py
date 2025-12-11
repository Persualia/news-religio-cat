from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.iscreb import ISCREBScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed() -> BeautifulSoup:
    xml = (FIXTURES / "iscreb_feed.xml").read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = ISCREBScraper()
    soup = load_feed()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert first.title == "Paraula i joc: didàctica creativa de la Bíblia"
    assert first.url == "https://www.iscreb.org/ca/node/13376"
    assert "didàctica creativa" in first.summary
    assert first.published_at == datetime(2025, 12, 10, 12, 6, 59, tzinfo=timezone.utc)
