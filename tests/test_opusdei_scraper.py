from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.opusdei import OpusDeiScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed() -> BeautifulSoup:
    xml = (FIXTURES / "opusdei_feed.xml").read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = OpusDeiScraper()
    soup = load_feed()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert first.title == "Michelle, el Líban: «La visita del Papa ens ha portat esperança»"
    assert (
        first.url
        == "https://opusdei.org/ca-es/article/michelle-liban-la-visita-del-papa-ens-ha-portat-esperanca"
    )
    assert "explosió al port de Beirut" in first.summary
    assert first.published_at == datetime(2025, 12, 10, 11, 40, 39, 719219, tzinfo=timezone.utc)
    assert first.metadata["lang"] == "ca"
