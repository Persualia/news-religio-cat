import json
from datetime import datetime, timezone
from pathlib import Path

from scraping.justiciaipau import JusticiaIPauScraper

FIXTURES = Path(__file__).parent / "fixtures"


class _DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_extract_items_from_api(monkeypatch):
    scraper = JusticiaIPauScraper()
    payload = json.loads((FIXTURES / "justiciaipau_posts.json").read_text(encoding="utf-8"))

    monkeypatch.setattr(scraper, "_get", lambda url: _DummyResponse(payload))

    items = list(scraper.extract_items(None))  # type: ignore[arg-type]

    assert len(items) == len(payload)

    first = items[0]
    assert (
        first.title
        == "Gabriela Serra rebrà el guardó del Memorial per la Pau Joan XXIII i el projecte Top Manta, la Menció Frederic Roda 2025"
    )
    assert (
        first.url
        == "https://justiciaipau.org/gabriela-serra-rebra-el-guardo-del-memorial-per-la-pau-joan-xxiii-i-el-projecte-top-manta-la-mencio-frederic-roda-2025"
    )
    assert first.summary.startswith("El Comitè de concessió de la Universitat Internacional de la Pau")
    assert first.published_at == datetime(2025, 12, 2, 12, 26, 41, tzinfo=timezone.utc)
    assert first.metadata["base_url"] == scraper.base_url
    assert first.metadata["lang"] == scraper.default_lang
    assert first.metadata["published_at"] == "2025-12-02T12:26:41+00:00"

    second = items[1]
    assert second.summary.startswith("El proper dilluns 1 de desembre, de 10 h a 13 h")
