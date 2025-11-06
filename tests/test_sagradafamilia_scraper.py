from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.sagradafamilia import SagradaFamiliaScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing_without_portlet_fetch():
    scraper = SagradaFamiliaScraper()
    soup = load_fixture("sagradafamilia_listing.html")

    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "Conferència sobre l’espiritualitat de Gaudí",
        "Es col·loca el primer element de la creu",
        "Carta del rector",
    ]
    assert [item.url for item in items] == [
        "https://sagradafamilia.org/-/conferencia-sobre-l-espiritualitat-de-gaudi",
        "https://sagradafamilia.org/-/es-col-loca-primer-element-creu",
        "https://sagradafamilia.org/-/carta-del-rector",
    ]
    assert all(item.summary == item.url for item in items)
    assert all(item.source == "sagradafamilia" for item in items)

    assert items[0].published_at == datetime(2025, 11, 4, tzinfo=timezone.utc)
    assert items[1].published_at == datetime(2025, 11, 3, tzinfo=timezone.utc)
    assert items[2].published_at == datetime(2025, 11, 2, tzinfo=timezone.utc)


def test_extract_items_sets_metadata():
    scraper = SagradaFamiliaScraper()
    soup = load_fixture("sagradafamilia_listing.html")

    items = list(scraper.extract_items(soup))
    item = items[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-11-04T00:00:00+00:00"
    assert items[2].metadata["published_at"] == "2025-11-02T00:00:00+00:00"
