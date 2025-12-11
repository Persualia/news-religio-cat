from datetime import datetime, timezone
from pathlib import Path
import json

from bs4 import BeautifulSoup

from scraping.oar import OARScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_listing() -> BeautifulSoup:
    html = (FIXTURES / "oar_listing.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def load_api_payload() -> dict:
    return json.loads((FIXTURES / "oar_api.json").read_text(encoding="utf-8"))


class DummyOARScraper(OARScraper):
    def __init__(self, payload: dict):
        super().__init__()
        self._payload = payload
        self.called_urls: list[str] = []

    def _fetch_api_response(self, api_url: str) -> dict:
        self.called_urls.append(api_url)
        return self._payload


def test_extract_items_from_listing_and_api():
    scraper = DummyOARScraper(load_api_payload())
    soup = load_listing()

    items = list(scraper.extract_items(soup))

    assert scraper.called_urls == [
        "https://ajuntament.barcelona.cat/oficina-afers-religiosos/ca/api/noticies/node/1?xout=json2&wtarget=oficina-afers-religiosos&nr=10&lg=ca&from=0"
    ]

    assert len(items) == 2

    first = items[0]
    assert first.title == "Nadal(s): Barcelona celebra la pluralitat cristiana de la ciutat"
    assert first.url.endswith(
        "/oficina-afers-religiosos/ca/noticies/nadals-barcelona-celebra-la-pluralitat-cristiana-de-la-ciutat-1575040"
    )
    assert first.summary == "Activitats del 2 al 23 de desembre."
    assert first.published_at == datetime(2025, 11, 20, 8, 34, tzinfo=timezone.utc)
    assert first.metadata["published_at"] == "2025-11-20T08:34:00+00:00"

    second = items[1]
    assert second.title.startswith("Estratègies i eines")
    assert second.url.endswith("estrategies-i-enes-de-financament-public-claus-per-accedir-a-subvencions-1574686")
