from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.caritasgirona import CaritasGironaScraper, extract_published_at, extract_summary

FIXTURES = Path(__file__).parent / "fixtures"


def _soup(name: str) -> BeautifulSoup:
    return BeautifulSoup((FIXTURES / name).read_text(encoding="utf-8"), "lxml")


def test_extract_items_from_listing(monkeypatch):
    scraper = CaritasGironaScraper()
    article = _soup("caritasgirona_article.html")
    requested: list[str] = []

    def fake_get_soup(url):
        requested.append(url)
        return article

    monkeypatch.setattr(scraper, "_get_soup", fake_get_soup)

    items = list(scraper.extract_items(_soup("caritasgirona_listing.html")))

    assert len(items) == 9
    first = items[0]
    assert first.title == "Nova edició de la campanya Ningú Sense Llar"
    assert first.url == "https://www.caritasgirona.cat/noticias/nova-edicio-de-la-campanya-ningu-sense-llar"
    assert first.summary.startswith("Tal com ja és habitual per aquestes dates")
    assert first.published_at == datetime(2026, 11, 18, 11, 4, 10, tzinfo=timezone.utc)
    assert first.metadata["lang"] == "ca"
    assert requested[0] == first.url
    assert len(set(requested)) == 9


def test_detail_fetch_failure_keeps_item(monkeypatch):
    scraper = CaritasGironaScraper()

    def failing_get_soup(url):
        raise RuntimeError("boom")

    monkeypatch.setattr(scraper, "_get_soup", failing_get_soup)

    items = list(scraper.extract_items(_soup("caritasgirona_listing.html")))

    assert len(items) == 9
    assert items[0].summary == items[0].url
    assert "published_at" not in items[0].metadata


def test_published_at_falls_back_to_header_date():
    article = _soup("caritasgirona_article.html")
    for script in article.select('script[type="application/ld+json"]'):
        script.decompose()

    assert extract_published_at(article) == datetime(2026, 11, 18, tzinfo=timezone.utc)
    assert extract_summary(article)
