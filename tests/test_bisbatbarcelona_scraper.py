from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.bisbatbarcelona import BisbatBarcelonaScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = BisbatBarcelonaScraper()
    soup = load_fixture("bisbatbarcelona_listing.html")

    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "Nova edició de Sembradors d’Estels",
        "Papa Lleó XIV",
    ]
    assert [item.url for item in items] == [
        "https://esglesia.barcelona/actualitat/nova-edicio-sembradors-estels",
        "https://esglesia.barcelona/actualitat/papa-lleo-xiv",
    ]
    assert all(item.summary == item.url for item in items)
    assert all(item.source == "bisbatbarcelona" for item in items)

    assert items[0].published_at == datetime(2025, 11, 5, tzinfo=timezone.utc)
    assert items[1].published_at == datetime(2025, 11, 4, tzinfo=timezone.utc)


def test_extract_items_sets_metadata():
    scraper = BisbatBarcelonaScraper()
    soup = load_fixture("bisbatbarcelona_listing.html")

    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-11-05T00:00:00+00:00"
