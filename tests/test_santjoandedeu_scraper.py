from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.santjoandedeu import SantJoanDeDeuScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(text, "lxml")


def test_extract_items_from_listing():
    scraper = SantJoanDeDeuScraper()
    soup = load_fixture("santjoandedeu_listing.json")

    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "Salud mental y sinhogarismo centra la cuarta edición de R-Conecta",
        "EthiCare’25 reunirá a más de 300 personas expertas y profesionales de San Juan de Dios España y Fundación Hospitalarias en Barcelona",
    ]
    assert [item.url for item in items] == [
        "https://sjd.es/salud-mental-y-sinhogarismo-centra-la-cuarta-edicion-de-r-conecta",
        "https://sjd.es/ethicare25-reunira-a-mas-de-300-personas-expertas-y-profesionales-de-san-juan-de-dios-espana-y-fundacion-hospitalarias-en-barcelona",
    ]
    assert all(item.summary == item.url for item in items)
    assert all(item.source == "santjoandedeu" for item in items)

    assert items[0].published_at == datetime(2025, 11, 5, 13, 35, 53, tzinfo=timezone.utc)
    assert items[1].published_at == datetime(2025, 11, 3, 15, 36, 30, tzinfo=timezone.utc)


def test_extract_items_sets_metadata():
    scraper = SantJoanDeDeuScraper()
    soup = load_fixture("santjoandedeu_listing.json")

    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-11-05T13:35:53+00:00"
