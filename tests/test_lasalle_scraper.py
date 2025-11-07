from pathlib import Path

from bs4 import BeautifulSoup

from scraping.lasalle import LaSalleScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    xml = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = LaSalleScraper()
    soup = load_fixture("lasalle_feed.xml")
    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == ["Primera notícia La Salle", "Segona notícia La Salle"]
    assert [item.url for item in items] == [
        "https://lasalle.cat/primera-noticia",
        "https://lasalle.cat/segona-noticia",
    ]
    assert [item.summary for item in items] == ["Resum primera", "Resum segona"]
    assert all(item.source == "lasalle" for item in items)


def test_extract_items_sets_metadata():
    scraper = LaSalleScraper()
    soup = load_fixture("lasalle_feed.xml")
    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2024-11-06T08:00:00+00:00"
