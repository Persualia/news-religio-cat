from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.salesians import SalesiansScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_article_urls():
    scraper = SalesiansScraper()
    soup = load_fixture("salesians_listing.html")
    urls = list(scraper.extract_article_urls(soup))
    assert urls == [
        "https://salesianos.info/blog/primera-noticia/",
        "https://salesianos.info/blog/segona-noticia/",
    ]


def test_parse_article_success():
    scraper = SalesiansScraper()
    soup = load_fixture("salesians_article.html")
    article = scraper.parse_article(
        soup,
        "https://www.salesians.cat/noticia/primera-noticia/",
    )
    assert article.site == "salesians"
    assert article.base_url == scraper.base_url
    assert article.lang == "ca"
    assert article.title == "Celebració de la comunitat salesiana"
    assert "Primer paràgraf" in article.content
    assert (
        article.description
        == "El passat 12 de setembre, els Salesians Cooperadors (SSCC) van llançar oficialment el seu projecte d'animació per a la Regió Ibèrica en el curs 2025-2026, proposant el lema “Feliços els humils”."
    )
    assert article.author == "Salesians Comunicació"
    assert article.published_at == datetime(2025, 9, 15, tzinfo=timezone.utc)
