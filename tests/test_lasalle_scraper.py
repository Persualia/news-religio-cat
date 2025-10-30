from pathlib import Path

from bs4 import BeautifulSoup

from scraping.lasalle import LaSalleScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = LaSalleScraper()
    soup = load_fixture("lasalle_listing.html")
    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == ["Primera notícia La Salle", "Segona notícia La Salle"]
    assert [item.url for item in items] == [
        "https://lasalle.cat/primera-noticia",
        "https://lasalle.cat/segona-noticia",
    ]
    assert all(item.summary == item.url for item in items)
    assert all(item.source == "lasalle" for item in items)


def test_extract_items_sets_metadata():
    scraper = LaSalleScraper()
    soup = load_fixture("lasalle_listing.html")
    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
