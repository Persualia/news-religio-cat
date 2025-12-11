from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.blanquerna import BlanquernaScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = BlanquernaScraper()
    soup = load_fixture("blanquerna_listing.html")

    items = list(scraper.extract_items(soup))

    assert len(items) == 1
    item = items[0]
    assert item.title == "Notícia Blanquerna"
    assert item.url == "https://www.blanquerna.edu/ca/noticies/noticia-blanquerna"
    assert item.summary == "Resum notícia."
    assert item.published_at == datetime(2025, 12, 9, 12, 0, tzinfo=timezone.utc)
    assert item.metadata["published_at"] == "2025-12-09T12:00:00+00:00"
