from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.bisbatsolsona import BisbatSolsonaScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = BisbatSolsonaScraper()
    soup = load_fixture("bisbatsolsona_listing.html")
    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "Primera notícia Bisbat Solsona",
        "Segona notícia Bisbat Solsona",
    ]
    assert [item.url for item in items] == [
        "https://bisbatsolsona.cat/2025/10/primera-noticia",
        "https://bisbatsolsona.cat/2025/10/segona-noticia",
    ]
    assert all(item.summary == item.url for item in items)
    assert all(item.source == "bisbatsolsona" for item in items)

    expected_first = datetime.fromisoformat("2025-10-28T08:55:40+00:00").astimezone(timezone.utc)
    expected_second = datetime.fromisoformat("2025-10-27T14:43:22+00:00").astimezone(timezone.utc)
    assert items[0].published_at == expected_first
    assert items[1].published_at == expected_second


def test_extract_items_sets_metadata():
    scraper = BisbatSolsonaScraper()
    soup = load_fixture("bisbatsolsona_listing.html")
    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-10-28T08:55:40+00:00"
