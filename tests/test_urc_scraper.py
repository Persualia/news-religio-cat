from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.urc import URCScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed(name: str) -> BeautifulSoup:
    xml = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = URCScraper()
    soup = load_feed("urc_feed.xml")

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert first.title == "Montserrat tanca el Mil·lenari amb una gran pregària coral d’acció de gràcies"
    assert (
        first.url
        == "https://urc.cat/montserrat-tanca-el-millenari-amb-una-gran-pregaria-coral-daccio-de-gracies"
    )
    assert "Montserrat tanca el Mil·lenari" in first.summary
    assert first.published_at == datetime(2025, 12, 9, 12, 21, 56, tzinfo=timezone.utc)
    assert first.metadata["published_at"] == "2025-12-09T12:21:56+00:00"
