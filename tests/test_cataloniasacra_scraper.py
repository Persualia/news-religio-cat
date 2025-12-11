from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.cataloniasacra import CataloniaSacraScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_listing() -> BeautifulSoup:
    html = (FIXTURES / "cataloniasacra_listing.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = CataloniaSacraScraper()
    soup = load_listing()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert (
        first.title
        == "El Consell Comarcal del Baix Ebre promou el patrimoni religiós de Jesús amb tours virtuals"
    )
    assert (
        first.url
        == "https://www.cataloniasacra.cat/noticies/detall/noticies_detall/265"
    )
    assert first.summary.startswith("El Consell Comarcal del Baix Ebre ha desenvolupat tours virtuals")
    assert first.published_at == datetime(2025, 12, 8, tzinfo=timezone.utc)
