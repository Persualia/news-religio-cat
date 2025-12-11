from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.acat import ACATScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed() -> BeautifulSoup:
    xml = (FIXTURES / "acat_feed.xml").read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = ACATScraper()
    soup = load_feed()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert first.title == "Manifest contra el pacte aranzelari UE-EUA"
    assert first.url == "https://acat.pangea.org/manifest-contra-el-pacte-aranzelari-ue-eua"
    assert "Pacte Aranzelari" in first.summary
    assert first.published_at == datetime(2025, 11, 25, 16, 43, 8, tzinfo=timezone.utc)
