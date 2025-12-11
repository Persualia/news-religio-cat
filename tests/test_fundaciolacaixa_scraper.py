from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.fundaciolacaixa import FundacioLaCaixaScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_listing() -> BeautifulSoup:
    html = (FIXTURES / "fundaciolacaixa_listing.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = FundacioLaCaixaScraper()
    soup = load_listing()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert items
    first = items[0]
    assert first.title.startswith("María Angustias Salmerón")
    assert first.url.endswith("maria-angustias-salmeron-benestar-digital-infancia-adolescencia-7844.html")
    assert "impacte dels mitjans digitals" in first.summary.lower()
    assert first.published_at == datetime(2025, 12, 9, tzinfo=timezone.utc)
