from datetime import datetime, timezone
import json
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.escolapia import EscolaPiaScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def load_api_fixture(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_extract_items_from_listing():
    scraper = EscolaPiaScraper()
    soup = load_fixture("escolapia_listing.html")
    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "Primera notícia Escola Pia",
        "Segona notícia Escola Pia",
    ]
    assert [item.url for item in items] == [
        "https://escolapia.cat/actualitat/primera-noticia",
        "https://escolapia.cat/actualitat/segona-noticia",
    ]
    assert all(item.summary == item.url for item in items)
    assert all(item.source == "escolapia" for item in items)

    assert items[0].published_at == datetime(2025, 10, 29, tzinfo=timezone.utc)
    assert items[1].published_at == datetime(2025, 10, 27, tzinfo=timezone.utc)


def test_extract_items_sets_metadata():
    scraper = EscolaPiaScraper()
    soup = load_fixture("escolapia_listing.html")
    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-10-29T00:00:00+00:00"


def test_extract_items_from_api_payload():
    scraper = EscolaPiaScraper()
    payload = load_api_fixture("escolapia_api.json")

    items = scraper._extract_items_from_api_payload(payload)

    assert [item.title for item in items] == [
        "Toni Aguilar, nou director general de Centres Concertats i Privats",
        "“L’orientació: de l’aula al món professional”, nova jornada de l’FP",
    ]
    assert [item.url for item in items] == [
        "https://escolapia.cat/actualitat/toni-aguilar-nou-director-general-de-centres-concertats-i-privats",
        "https://escolapia.cat/actualitat/lorientacio-de-laula-al-mon-professional-nova-jornada-de-lfp",
    ]
    assert items[0].published_at == datetime(2026, 4, 1, 18, 5, tzinfo=timezone.utc)
    assert items[1].metadata["published_at"] == "2026-03-26T09:00:00+00:00"
