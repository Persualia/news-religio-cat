from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
import pytest

from scraping.base import ScraperUnexpectedContentError
from scraping.bisbatsantfeliu import BisbatSantFeliuScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(text, "lxml")


def test_extract_items_from_listing():
    scraper = BisbatSantFeliuScraper()
    soup = load_fixture("bisbatsantfeliu_listing.json")

    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "XX Jornades de Formació i Animació Pastoral",
        "Trobada de formació a Santa Maria de Lavern",
    ]
    assert [item.url for item in items] == [
        "https://bisbatsantfeliu.cat/xx-jornades-de-formacio-i-animacio-pastoral",
        "https://bisbatsantfeliu.cat/trobada-de-formacio-a-santa-maria-de-lavern",
    ]
    assert all(item.summary == item.url for item in items)
    assert all(item.source == "bisbatsantfeliu" for item in items)

    assert items[0].published_at == datetime(2025, 11, 6, 10, 45, 53, tzinfo=timezone.utc)
    assert items[1].published_at == datetime(2025, 11, 5, 13, 50, 34, tzinfo=timezone.utc)


def test_extract_items_sets_metadata():
    scraper = BisbatSantFeliuScraper()
    soup = load_fixture("bisbatsantfeliu_listing.json")

    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-11-06T10:45:53+00:00"


def test_extract_items_rejects_non_json_listing():
    scraper = BisbatSantFeliuScraper()
    soup = BeautifulSoup("<html><title>Forbidden</title><body>Access denied</body></html>", "lxml")

    with pytest.raises(ScraperUnexpectedContentError) as exc_info:
        list(scraper.extract_items(soup))

    assert exc_info.value.site_id == "bisbatsantfeliu"
    assert "no devolvió JSON válido" in exc_info.value.detail
