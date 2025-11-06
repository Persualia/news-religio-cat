from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.bisbatterrassa import BisbatTerrassaScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(text, "lxml")


def test_extract_items_from_listing():
    scraper = BisbatTerrassaScraper()
    soup = load_fixture("bisbatterrassa_listing.json")

    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "Mn Emili Marlés rep el guardó Alter Christus en la categoria de nova evangelització",
        "XIII Jornades Transmet: “Crec en l’Església”",
    ]
    assert [item.url for item in items] == [
        "https://www.bisbatdeterrassa.org/xiii-jornades-transmet-crec-en-lesglesia-2",
        "https://www.bisbatdeterrassa.org/xiii-jornades-transmet-crec-en-lesglesia",
    ]
    assert all(item.summary == item.url for item in items)
    assert all(item.source == "bisbatterrassa" for item in items)

    assert items[0].published_at == datetime(2025, 11, 5, 10, 14, 25, tzinfo=timezone.utc)
    assert items[1].published_at == datetime(2025, 10, 29, 10, 42, 50, tzinfo=timezone.utc)


def test_extract_items_sets_metadata():
    scraper = BisbatTerrassaScraper()
    soup = load_fixture("bisbatterrassa_listing.json")

    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-11-05T10:14:25+00:00"
