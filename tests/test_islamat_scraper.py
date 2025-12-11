from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.islamat import IslamatScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed(name: str) -> BeautifulSoup:
    xml = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = IslamatScraper()
    soup = load_feed("islamat_feed.xml")

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert (
        first.title
        == "Alivio, gratitud y unidad: la comunidad musulmana celebra el archivo de la causa por financiación del terrorismo"
    )
    assert (
        first.url
        == "https://islamcat.org/alivio-gratitud-y-unidad-la-comunidad-musulmana-celebra-el-archivo-de-la-causa-por-financiacion-del-terrorismo"
    )
    assert first.summary.startswith("islamcal.bcn 2 de diciembre de 2025")
    assert first.published_at == datetime(2025, 12, 2, 15, 49, 49, tzinfo=timezone.utc)
    assert first.metadata["base_url"] == scraper.base_url
    assert first.metadata["lang"] == scraper.default_lang
    assert first.metadata["published_at"] == "2025-12-02T15:49:49+00:00"
