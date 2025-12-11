from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.migrastudium import MigrastudiumScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = MigrastudiumScraper()
    soup = load_fixture("migrastudium_listing.html")

    expected_dates = {
        "https://www.migrastudium.org/actualitat/les-nostres-mans-diuen-prou": datetime(2025, 11, 25, tzinfo=timezone.utc),
        "https://www.migrastudium.org/actualitat/presencia-que-teixeix-humanitat-alla-tot-es-trenca": datetime(2025, 10, 6, tzinfo=timezone.utc),
        "https://www.migrastudium.org/actualitat/primera-setmana-doctubre-una-cita-amb-el-centre-dinternament-destrangers": datetime(2025, 9, 16, tzinfo=timezone.utc),
    }

    scraper._fetch_published_at = lambda url: expected_dates.get(url)

    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "Les nostres mans diuen prou!",
        "Presència que teixeix humanitat allà on tot es trenca",
        "Primera setmana d'octubre, una cita amb el CIE",
    ]
    assert [item.url for item in items] == list(expected_dates.keys())
    assert [item.summary for item in items] == [
        "Avui, 25-N, Dia Internacional per l'Erradicació...",
        "Més de 250 persones ens vam aplegar...",
        "Presentació de l'Informe CIE SJM 2024 a Barcelona...",
    ]
    assert [item.published_at for item in items] == list(expected_dates.values())
    assert all(item.source == "migrastudium" for item in items)


def test_extract_items_sets_metadata():
    scraper = MigrastudiumScraper()
    soup = load_fixture("migrastudium_listing.html")

    scraper._fetch_published_at = lambda url: datetime(2025, 11, 25, tzinfo=timezone.utc)

    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-11-25T00:00:00+00:00"
