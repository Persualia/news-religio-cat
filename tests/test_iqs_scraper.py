from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
import httpx

from scraping.iqs import IQSScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_feed(name: str) -> BeautifulSoup:
    xml = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(xml, "xml")


def test_extract_items_from_feed():
    scraper = IQSScraper()
    soup = load_feed("iqs_feed.xml")

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert (
        first.title
        == "IQS School of Management es consolida al Top 100 de les millors escoles de negocis d’Europa, segons el Financial Times"
    )
    assert (
        first.url
        == "https://iqs.edu/ca/iqs/noticies/iqs-school-of-management-es-consolida-al-top-100-de-les-millors-escoles-de-negocis-deuropa-segons-el-financial-times"
    )
    assert first.summary.startswith("IQS School of Management reafirma la seva excel·lència acadèmica")
    assert first.published_at == datetime(2025, 12, 11, 10, 58, 41, tzinfo=timezone.utc)
    assert first.metadata["base_url"] == scraper.base_url
    assert first.metadata["lang"] == scraper.default_lang
    assert first.metadata["published_at"] == "2025-12-11T10:58:41+00:00"


def test_get_retries_without_ssl_verification_on_certificate_failure(monkeypatch):
    scraper = IQSScraper()
    expected = httpx.Response(200, text="<rss></rss>", request=httpx.Request("GET", scraper.listing_url))

    def fail_verified(url: str):
        raise httpx.ConnectError(
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(scraper._client, "get", fail_verified)
    monkeypatch.setattr(scraper._insecure_client, "get", lambda url: expected)

    response = scraper._get(scraper.listing_url)

    assert response is expected


def test_get_does_not_retry_without_ssl_verification_on_other_connect_error(monkeypatch):
    scraper = IQSScraper()

    def fail_verified(url: str):
        raise httpx.ConnectError("network down", request=httpx.Request("GET", url))

    monkeypatch.setattr(scraper._client, "get", fail_verified)

    try:
        scraper._get(scraper.listing_url)
    except httpx.ConnectError as exc:
        assert "network down" in str(exc)
    else:
        raise AssertionError("Expected ConnectError")
