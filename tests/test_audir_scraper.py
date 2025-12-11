from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.audir import AudirScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed() -> BeautifulSoup:
    xml = (FIXTURES / "audir_feed.xml").read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = AudirScraper()
    soup = load_feed()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert first.title == "18 d’octubre: La Nit de les Religions de Mataró"
    assert first.url == "https://audir.org/18-doctubre-la-nit-de-les-religions-de-mataro"
    assert "La Nit de les Religions" in first.summary
    assert first.published_at == datetime(2025, 10, 10, 8, 51, 27, tzinfo=timezone.utc)
    assert first.metadata["published_at"] == "2025-10-10T08:51:27+00:00"
