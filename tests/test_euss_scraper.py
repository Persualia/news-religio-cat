from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.euss import EUSSScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed(name: str) -> BeautifulSoup:
    xml = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = EUSSScraper()
    soup = load_feed("euss_feed.xml")

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert first.title == "Alumnes d’Energies Renovables de l’EUSS visiten la Planta de Biometanització de Can Barba"
    assert (
        first.url
        == "https://neussletter.4veuss.com/2025/12/11/alumnes-energies-renovables-euss-visiten-planta-biometanitzacio-can-barba"
    )
    assert first.summary.startswith("En el marc de l’assignatura ‘Generació Elèctrica’")
    assert first.published_at == datetime(2025, 12, 11, 8, 54, 50, tzinfo=timezone.utc)
    assert first.metadata["base_url"] == scraper.base_url
    assert first.metadata["lang"] == scraper.default_lang
    assert first.metadata["published_at"] == "2025-12-11T08:54:50+00:00"
