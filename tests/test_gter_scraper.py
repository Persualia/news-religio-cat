from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.gter import GTERScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed(name: str) -> BeautifulSoup:
    xml = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = GTERScraper()
    soup = load_feed("gter_feed.xml")

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert first.title == "SUPORT AL MANIFEST DE LA COMUNITAT MUSULMANA"
    assert (
        first.url
        == "https://www.grupdereligions.org/suport-al-manifest-de-la-comunitat-musulmana"
    )
    assert first.summary.startswith("SUPORT AL MANIFEST DE LA COMUNITAT MUSULMANA")
    assert first.published_at == datetime(2025, 7, 13, 20, 15, 32, tzinfo=timezone.utc)
    assert first.metadata["base_url"] == scraper.base_url
    assert first.metadata["lang"] == scraper.default_lang
    assert first.metadata["published_at"] == "2025-07-13T20:15:32+00:00"
