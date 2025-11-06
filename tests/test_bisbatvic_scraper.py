from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.bisbatvic import BisbatVicScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = BisbatVicScraper()
    soup = load_fixture("bisbatvic_listing.html")

    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "Ajudeu-nos a complir amb més fidelitat la voluntat de Déu",
        "Litúrgia en família",
    ]
    assert [item.url for item in items] == [
        "https://www.bisbatvic.org/ca/noticia/ajudeu-nos-complir-amb-mes-fidelitat-la-voluntat-de-deu",
        "https://www.bisbatvic.org/ca/noticia/liturgia-en-familia",
    ]
    assert all(item.summary == item.url for item in items)
    assert all(item.source == "bisbatvic" for item in items)

    assert items[0].published_at == datetime(2025, 11, 6, tzinfo=timezone.utc)
    assert items[1].published_at == datetime(2025, 10, 31, tzinfo=timezone.utc)


def test_extract_items_sets_metadata():
    scraper = BisbatVicScraper()
    soup = load_fixture("bisbatvic_listing.html")
    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-11-06T00:00:00+00:00"
