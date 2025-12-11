from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.dgar import DGARScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_listing() -> BeautifulSoup:
    html = (FIXTURES / "dgar_listing.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = DGARScraper()
    soup = load_listing()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert (
        first.url
        == "https://afersreligiosos.gencat.cat/ca/actualitat/noticies/resolucio-convocatoria-recerca"
    )
    assert first.title == "Publicada la resolució de concessió de la convocatòria de recerca"
    assert first.published_at == datetime(2025, 12, 4, tzinfo=timezone.utc)
    assert first.metadata["published_at"] == "2025-12-04T00:00:00+00:00"
