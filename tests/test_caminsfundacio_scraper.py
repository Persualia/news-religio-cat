from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.caminsfundacio import CaminsFundacioScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = CaminsFundacioScraper()
    soup = load_fixture("caminsfundacio_listing.html")

    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "20 anys de feina per l’acollida de persones migrades",
        "Les activitats de lleure són un dret, no un privilegi",
        "Les receptes de Calassanci: quan la cuina és transformadora",
    ]
    assert [item.url for item in items] == [
        "https://www.caminsfundacio.org/20-anys-de-feina-per-lacollida-de-persones-migrades",
        "https://www.caminsfundacio.org/les-activitats-de-lleure-son-un-dret-no-un-privilegi",
        "https://www.caminsfundacio.org/les-receptes-de-calassanci-quan-la-cuina-es-transformadora",
    ]
    assert [item.summary for item in items] == [
        "El dijous 20 de novembre es va celebrar una jornada molt especial.",
        "Aquesta setmana, al Telenotícies a 3CatInfo, s’ha destacat la importància del lleure.",
        "Onze receptes que uneixen cultures i històries.",
    ]
    assert [item.published_at for item in items] == [
        datetime(2025, 11, 21, tzinfo=timezone.utc),
        datetime(2025, 11, 13, tzinfo=timezone.utc),
        datetime(2025, 11, 3, tzinfo=timezone.utc),
    ]
    assert all(item.source == "caminsfundacio" for item in items)


def test_metadata_contains_published_at():
    scraper = CaminsFundacioScraper()
    soup = load_fixture("caminsfundacio_listing.html")

    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-11-21T00:00:00+00:00"
