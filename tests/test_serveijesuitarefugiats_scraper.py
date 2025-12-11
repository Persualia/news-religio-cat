from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.serveijesuitarefugiats import ServeiJesuitaRefugiatsScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = ServeiJesuitaRefugiatsScraper()
    soup = load_fixture("serveijesuitarefugiats_listing.html")

    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "Esperanza en camino",
        "Acompañar en la incertidumbre",
        "Vidas que florecen",
    ]
    assert [item.url for item in items] == [
        "https://jrs.net/es/noticias/esperanza-en-camino",
        "https://jrs.net/es/historias/acompanar-en-incertidumbre",
        "https://jrs.net/es/noticias/vidas-que-florecen",
    ]
    assert all(item.summary == item.url for item in items)
    assert all(item.source == "serveijesuitarefugiats" for item in items)

    assert items[0].published_at == datetime(2025, 12, 9, tzinfo=timezone.utc)
    assert items[1].published_at == datetime(2025, 11, 4, tzinfo=timezone.utc)
    assert items[2].published_at == datetime(2025, 9, 15, tzinfo=timezone.utc)


def test_extract_items_sets_metadata():
    scraper = ServeiJesuitaRefugiatsScraper()
    soup = load_fixture("serveijesuitarefugiats_listing.html")

    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-12-09T00:00:00+00:00"
