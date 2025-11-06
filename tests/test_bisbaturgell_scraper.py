from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.bisbaturgell import BisbatUrgellScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = BisbatUrgellScraper()
    soup = load_fixture("bisbaturgell_listing.html")
    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "Primera notícia Bisbat Urgell",
        "Segona notícia Bisbat Urgell",
    ]
    assert [item.url for item in items] == [
        "https://bisbaturgell.org/ca/2025/10/primera-noticia",
        "https://bisbaturgell.org/ca/2025/10/segona-noticia",
    ]
    assert all(item.summary == item.url for item in items)
    assert all(item.source == "bisbaturgell" for item in items)

    expected_first = datetime(2025, 10, 30, tzinfo=timezone.utc)
    expected_second = datetime(2025, 10, 29, tzinfo=timezone.utc)
    assert items[0].published_at == expected_first
    assert items[1].published_at == expected_second


def test_extract_items_sets_metadata():
    scraper = BisbatUrgellScraper()
    soup = load_fixture("bisbaturgell_listing.html")
    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-10-30T00:00:00+00:00"
