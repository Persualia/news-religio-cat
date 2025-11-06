from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.bisbattortosa import BisbatTortosaScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(text, "lxml")


def test_extract_items_from_listing():
    scraper = BisbatTortosaScraper()
    soup = load_fixture("bisbattortosa_listing.json")

    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "“Tu també pots ser Sant”: Jornada de Germanor 2025",
        "L’ESGLÉSIA DIOCESANA: UN CANT SILENT D’AMOR 09-11-2025",
    ]
    assert [item.url for item in items] == [
        "https://www.bisbattortosa.org/tu-tambe-pots-ser-sant-jornada-de-germanor-2025",
        "https://www.bisbattortosa.org/lesglesia-diocesana-un-cant-silent-damor-09-11-2025",
    ]
    assert all(item.summary == item.url for item in items)
    assert all(item.source == "bisbattortosa" for item in items)

    assert items[0].published_at == datetime(2025, 11, 6, 11, 28, 37, tzinfo=timezone.utc)
    assert items[1].published_at == datetime(2025, 11, 6, 8, 0, tzinfo=timezone.utc)


def test_extract_items_sets_metadata():
    scraper = BisbatTortosaScraper()
    soup = load_fixture("bisbattortosa_listing.json")

    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-11-06T11:28:37+00:00"
