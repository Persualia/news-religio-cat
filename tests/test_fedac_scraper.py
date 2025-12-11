from datetime import datetime, timezone
from pathlib import Path

from scraping.fedac import FedacScraper

FIXTURES = Path(__file__).parent / "fixtures"


class _DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_extract_items_from_api(monkeypatch):
    scraper = FedacScraper()
    data = (FIXTURES / "fedac_posts.json").read_text(encoding="utf-8")

    import json

    payload = json.loads(data)

    monkeypatch.setattr(scraper, "_get", lambda url: _DummyResponse(payload))

    items = list(scraper.extract_items(None))  # type: ignore[arg-type]

    assert [item.title for item in items] == ["Notícia 1", "Notícia 2"]
    assert items[0].summary == "Resum 1"
    assert items[1].summary == "https://escoles.fedac.cat/noticia-2"
    assert items[0].published_at == datetime(2025, 12, 5, 10, 0, tzinfo=timezone.utc)
    assert items[1].published_at == datetime(2025, 11, 30, 8, 30, tzinfo=timezone.utc)
