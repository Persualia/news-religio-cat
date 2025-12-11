from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.caputxins import CaputxinsScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed() -> BeautifulSoup:
    xml = (FIXTURES / "caputxins_feed.xml").read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = CaputxinsScraper()
    soup = load_feed()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert first.title == "Butlletí de Sarrià 824 – Desembre 2025"
    assert first.url == "https://caputxins.cat/butlleti-de-sarria-824-desembre-2025"
    assert "butlletí" in first.summary.lower()
    assert first.published_at == datetime(2025, 12, 9, 16, 4, 43, tzinfo=timezone.utc)
