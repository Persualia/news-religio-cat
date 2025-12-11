from pathlib import Path

from bs4 import BeautifulSoup

from scraping.moenstirdelpoblet import MoenstirDelPobletScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_listing() -> BeautifulSoup:
    html = (FIXTURES / "poblet_listing.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = MoenstirDelPobletScraper()
    soup = load_listing()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert first.title == "DIRECTORI LITÚRGIC DE L'ORDE CISTERCENC 2026"
    assert (
        first.url
        == "https://www.poblet.cat/ca/actualitat/noticies/81/directori-liturgic-de-l-orde-cistercenc-2026"
    )
    assert first.summary == first.url
    assert first.metadata["base_url"] == scraper.base_url
    assert first.metadata["lang"] == scraper.default_lang
