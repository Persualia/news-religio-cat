from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.salesians import SalesiansScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "xml")


def test_extract_items_from_listing():
    scraper = SalesiansScraper()
    soup = load_fixture("salesians_feed.xml")
    items = list(scraper.extract_items(soup))
    assert [item.title for item in items] == ["Primera notícia", "Segona notícia"]
    assert [item.url for item in items] == [
        "https://salesianos.info/blog/primera-noticia",
        "https://salesianos.info/blog/segona-noticia",
    ]
    assert [item.published_at for item in items] == [
        datetime(2026, 5, 5, 11, 48, 26, tzinfo=timezone.utc),
        datetime(2026, 5, 4, 9, 15, tzinfo=timezone.utc),
    ]
    assert items[0].summary == "Contingut complet de la primera notícia."
    assert items[1].summary == "Resum de la segona notícia."
    assert all(item.source == "salesians" for item in items)


def test_extract_items_sets_metadata():
    scraper = SalesiansScraper()
    soup = load_fixture("salesians_feed.xml")
    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2026-05-05T11:48:26+00:00"
