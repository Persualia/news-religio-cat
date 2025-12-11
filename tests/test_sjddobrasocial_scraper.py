from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.sjddobrasocial import SJDDObraSocialScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = SJDDObraSocialScraper()
    soup = load_fixture("sjddobrasocial_listing.html")

    items = list(scraper.extract_items(soup))

    assert len(items) == 1
    item = items[0]

    assert item.title == "Cuando la soledad duele"
    assert item.url == "https://solidaritat.santjoandedeu.org/cuando-la-soledad-duele"
    assert item.summary == "Resumen breve del artículo."
    assert item.published_at == datetime(2025, 12, 1, tzinfo=timezone.utc)
    assert item.metadata["published_at"] == "2025-12-01T00:00:00+00:00"
