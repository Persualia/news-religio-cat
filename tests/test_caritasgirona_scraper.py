from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.caritasgirona import CaritasGironaScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_listing() -> BeautifulSoup:
    html = (FIXTURES / "caritasgirona_listing.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = CaritasGironaScraper()
    soup = load_listing()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert (
        first.title
        == "El projecte L’Obrador de Càritas Diocesana de Girona guardonat als Premis Josep Gassó Espina"
    )
    assert (
        first.url
        == "https://www.caritasgirona.cat/ca/4388/el-projecte-l’obrador-de-caritas-diocesana-de-girona-guardonat-als-premis-josep-gasso-espina.html"
    )
    assert "Fundació Catalana de l’Esplai" in first.summary
    assert first.published_at == datetime(2025, 12, 2, tzinfo=timezone.utc)
    assert first.metadata["lang"] == "ca"
