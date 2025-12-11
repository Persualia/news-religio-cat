from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.caritastarragona import CaritasTarragonaScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed() -> BeautifulSoup:
    xml = (FIXTURES / "caritastarragona_feed.xml").read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = CaritasTarragonaScraper()
    soup = load_feed()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert (
        first.title
        == "La dignitat humana de les dones: una defensa imprescindible en el Dia dels Drets Humans"
    )
    assert (
        first.url
        == "https://www.caritasdtarragona.cat/la-dignitat-humana-de-les-dones-una-defensa-imprescindible-en-el-dia-dels-drets-humans"
    )
    assert "drets humans" in first.summary.lower()
    assert first.published_at == datetime(2025, 12, 10, 11, 58, 48, tzinfo=timezone.utc)
    assert first.metadata["lang"] == "ca"
