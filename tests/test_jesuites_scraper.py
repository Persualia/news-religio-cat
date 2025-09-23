from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.jesuites import JesuitesScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_article_urls():
    scraper = JesuitesScraper()
    soup = load_fixture("jesuites_listing.html")
    urls = list(scraper.extract_article_urls(soup))
    assert urls == [
        "/ca/noticia/primera-noticia",
        "https://jesuites.net/ca/noticia/segona-noticia",
    ]


def test_parse_article_success():
    scraper = JesuitesScraper()
    soup = load_fixture("jesuites_article.html")
    article = scraper.parse_article(
        soup,
        "https://jesuites.net/ca/noticia/el-provincial-presenta-catalunya-el-nou-projecte-apostolic",
    )

    assert article.site == "jesuites"
    assert article.base_url == scraper.base_url
    assert article.lang == "ca"
    assert article.title == "El Provincial presenta a Catalunya el nou Projecte Apostòlic"
    assert "Impulsar la missió compartida amb laics" in article.content
    assert article.description is None
    assert article.author is None
    assert article.published_at == datetime(2025, 9, 21, tzinfo=timezone.utc)
