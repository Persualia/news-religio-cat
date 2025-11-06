from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.claretians import ClaretiansScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = ClaretiansScraper()
    soup = load_fixture("claretians_listing.html")
    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "Primera notícia Claretians",
        "Segona notícia Claretians",
    ]
    assert [item.url for item in items] == [
        "https://claretpaulus.org/ca/2025/10/30/primera-noticia",
        "https://claretpaulus.org/ca/2025/10/29/segona-noticia",
    ]
    assert all(item.summary == item.url for item in items)
    assert all(item.source == "claretians" for item in items)

    expected_first = datetime.fromisoformat("2025-10-30T16:46:40+02:00").astimezone(timezone.utc)
    expected_second = datetime.fromisoformat("2025-10-29T18:44:17+02:00").astimezone(timezone.utc)
    assert items[0].published_at == expected_first
    assert items[1].published_at == expected_second


def test_extract_items_sets_metadata():
    scraper = ClaretiansScraper()
    soup = load_fixture("claretians_listing.html")
    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-10-30T14:46:40+00:00"
