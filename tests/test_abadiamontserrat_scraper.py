from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.abadiamontserrat import AbadiaMontserratScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = AbadiaMontserratScraper()
    soup = load_fixture("abadiamontserrat_listing.html")

    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "Més d’un centenar d’usuaris de la Fundació Roure han visitat el Monestir per celebrar el Mil·lenari",
        "Homilia del P. Manel Gasch i Hurios, abat de Montserrat",
    ]
    assert [item.url for item in items] == [
        "https://www.millenarimontserrat.cat/noticia/540/centenar-usuaris-fundacio-roure-visitat-monestir-celebrar-millenari",
        "https://www.millenarimontserrat.cat/noticia/539/homilia-manel-gasch-hurios-abat-montserrat-novembre-2025",
    ]
    assert all(item.summary == item.url for item in items)
    assert all(item.source == "abadiamontserrat" for item in items)

    assert items[0].published_at == datetime(2025, 11, 5, tzinfo=timezone.utc)
    assert items[1].published_at == datetime(2025, 11, 3, tzinfo=timezone.utc)


def test_extract_items_sets_metadata():
    scraper = AbadiaMontserratScraper()
    soup = load_fixture("abadiamontserrat_listing.html")

    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-11-05T00:00:00+00:00"
