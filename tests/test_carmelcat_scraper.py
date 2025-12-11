from pathlib import Path

from bs4 import BeautifulSoup

from scraping.carmelcat import CarmelitesDescalcosScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_listing() -> BeautifulSoup:
    html = (FIXTURES / "carmelcat_listing.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = CarmelitesDescalcosScraper()
    soup = load_listing()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert first.title == "Trobada de comunitats a Tarragona"
    assert first.summary.startswith("El dimecres dia 10 de desembre")
    assert first.metadata["lang"] == "ca"

    assert first.url.startswith(scraper.listing_url)
