from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.escolapia import EscolaPiaScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = EscolaPiaScraper()
    soup = load_fixture("escolapia_listing.html")
    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "Primera notícia Escola Pia",
        "Segona notícia Escola Pia",
    ]
    assert [item.url for item in items] == [
        "https://escolapia.cat/actualitat/primera-noticia",
        "https://escolapia.cat/actualitat/segona-noticia",
    ]
    assert all(item.summary == item.url for item in items)
    assert all(item.source == "escolapia" for item in items)

    assert items[0].published_at == datetime(2025, 10, 29, tzinfo=timezone.utc)
    assert items[1].published_at == datetime(2025, 10, 27, tzinfo=timezone.utc)


def test_extract_items_sets_metadata():
    scraper = EscolaPiaScraper()
    soup = load_fixture("escolapia_listing.html")
    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-10-29T00:00:00+00:00"
