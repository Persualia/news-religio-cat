from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.fundacioproide import FundacioProideScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed() -> BeautifulSoup:
    xml = (FIXTURES / "fundacioproide_feed.xml").read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = FundacioProideScraper()
    soup = load_feed()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert first.title == "Samarreta Proide 2023"
    assert first.url == "https://www.fundacioproide.org/2023/02/01/samarreta-proide-2023"
    assert "samarretes" in first.summary.lower()
    assert first.published_at == datetime(2023, 2, 1, 10, 46, 41, tzinfo=timezone.utc)
