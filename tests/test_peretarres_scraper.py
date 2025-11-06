from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.peretarres import PeretarresScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = PeretarresScraper()
    soup = load_fixture("peretarres_listing.html")

    items = list(scraper.extract_items(soup))

    assert [item.title for item in items] == [
        "La Fundació Pere Tarrés reclama al Parlament més inversió en educació",
        "Infants del Raval en situació vulnerable reben revisions visuals gratuïtes gràcies a un projecte solidari",
        "La Fundació Pere Tarrés estrena noves instal·lacions al barri de Poble-sec",
    ]
    assert [item.url for item in items] == [
        "https://www.peretarres.org/actualitat/noticies/reclamem-al-parlament-mes-inversio-educacio",
        "https://www.peretarres.org/actualitat/noticies/promovem-revisions-visuals-gratuites-infants-raval",
        "https://www.peretarres.org/actualitat/noticies/estrenem-noves-aules-centre-socioeducatiu-poble-sec",
    ]
    assert all(item.summary == item.url for item in items)
    assert all(item.source == "peretarres" for item in items)

    assert items[0].published_at == datetime(2025, 10, 28, tzinfo=timezone.utc)
    assert items[1].published_at == datetime(2025, 10, 24, tzinfo=timezone.utc)
    assert items[2].published_at == datetime(2025, 10, 15, tzinfo=timezone.utc)


def test_extract_items_sets_metadata():
    scraper = PeretarresScraper()
    soup = load_fixture("peretarres_listing.html")

    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2025-10-28T00:00:00+00:00"
