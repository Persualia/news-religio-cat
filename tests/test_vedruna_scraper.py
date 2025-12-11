from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.vedruna import VedrunaScraper, _parse_catalan_date

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = VedrunaScraper()
    soup = load_fixture("vedruna_listing.html")

    items = list(scraper.extract_items(soup))

    assert len(items) == 1
    item = items[0]

    assert item.title.startswith("59 llibres recomanats")
    assert item.url == "https://vedruna.cat/59-llibres-recomanats-nadal-inspiracio-i-companyia-mesos-fred"
    assert item.summary == "Arribem a les portes de l’hivern..."
    assert item.published_at == datetime(2025, 12, 4, tzinfo=timezone.utc)
    assert item.metadata["published_at"] == "2025-12-04T00:00:00+00:00"


def test_parse_catalan_date_variants():
    date = _parse_catalan_date("14 de novembre de 2025")
    assert date == datetime(2025, 11, 14, tzinfo=timezone.utc)

    date = _parse_catalan_date("27 d'octubre de 2025")
    assert date == datetime(2025, 10, 27, tzinfo=timezone.utc)
