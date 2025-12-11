from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.fundaciocomtal import FundacioComtalScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = FundacioComtalScraper()
    soup = load_fixture("fundaciocomtal_listing.html")

    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "JÓVENES CON HOGAR, JÓVENES CON FUTURO",
        "TURISMO Y SOLIDARIDAD CON COOLTOURSPAIN",
        "DEPORTE Y SOLIDARIDAD EN EL 1ER TORNEO DE PADEL",
    ]
    assert [item.url for item in items] == [
        "https://comtal.org/es/jovenes-con-hogar-jovenes-con-futuro",
        "https://comtal.org/es/turismo-y-solidaridad-con-cooltourspain",
        "https://comtal.org/es/torneo-padel",
    ]
    assert all(item.summary == item.url for item in items)
    assert items[0].published_at == datetime(2025, 9, 30, tzinfo=timezone.utc)
    assert items[1].published_at == datetime(2025, 6, 10, tzinfo=timezone.utc)
    assert items[2].published_at == datetime(2025, 5, 27, tzinfo=timezone.utc)
    assert all(item.source == "fundaciocomtal" for item in items)


def test_extract_items_sets_metadata():
    scraper = FundacioComtalScraper()
    soup = load_fixture("fundaciocomtal_listing.html")

    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-09-30T00:00:00+00:00"
