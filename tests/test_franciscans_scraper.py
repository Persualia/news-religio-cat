from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.franciscans import FranciscansScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = FranciscansScraper()
    soup = load_fixture("franciscans_listing.html")

    items = list(scraper.extract_items(soup))

    assert len(items) == 1
    item = items[0]

    assert item.title == "Butlletí de Sarrià 824 – Desembre 2025"
    assert item.url == "https://caputxins.cat/wp-content/uploads/2025/12/FULL-INFORMATIU-SARRIA-824.pdf"
    assert item.summary == "Accedir al butlletí Horaris Advent i Nadal"
    assert item.published_at == datetime(2025, 12, 9, tzinfo=timezone.utc)
    assert item.metadata["published_at"] == "2025-12-09T00:00:00+00:00"
