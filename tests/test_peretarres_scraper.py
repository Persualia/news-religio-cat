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
        "Manel del Castillo, exdirector de l'Hospital Sant Joan de Déu, al Fòrum Pere Tarrés: “L’estat del benestar tal com el coneixem és en risc de col·lapse”",
        "400 monitors i monitores dels esplais MCECC de la Fundació Pere Tarrés treballen el sentiment de pertinença a una jornada a Premià de Mar",
        "La Facultat Pere Tarrés continua sent el millor centre universitari de l'Estat espanyol on estudiar Educació Social",
    ]
    assert [item.url for item in items] == [
        "https://www.peretarres.org/actualitat/noticies/manel-del-castillo-hospital-sant-joan-deu-estat-benestar-colapse",
        "https://www.peretarres.org/actualitat/noticies/400-monitors-i-monitores-dels-esplais-mcecc-fundacio-pere-tarres-treballen",
        "https://www.peretarres.org/actualitat/noticies/facultat-pere-tarres-millor-centre-universitari-estat-estudiar-educacio-social",
    ]
    assert all(item.summary == item.url for item in items)
    assert all(item.source == "peretarres" for item in items)

    assert items[0].published_at == datetime(2026, 6, 2, 12, tzinfo=timezone.utc)
    assert items[1].published_at == datetime(2026, 5, 18, 12, tzinfo=timezone.utc)
    assert items[2].published_at == datetime(2026, 5, 7, 12, tzinfo=timezone.utc)


def test_extract_items_sets_metadata():
    scraper = PeretarresScraper()
    soup = load_fixture("peretarres_listing.html")

    item = list(scraper.extract_items(soup))[0]

    assert item.metadata["base_url"] == scraper.base_url
    assert item.metadata["lang"] == scraper.default_lang
    assert item.metadata["published_at"] == "2026-06-02T12:00:00+00:00"


def test_extract_items_supports_legacy_listing_markup():
    scraper = PeretarresScraper()
    soup = BeautifulSoup(
        """
        <a class="titol-noticia-destacada" href="/actualitat/noticies/reclamem-al-parlament-mes-inversio-educacio">
          La Fundacio Pere Tarres reclama al Parlament mes inversio en educacio
        </a>
        <p class="btn btn-default font-20 mt-30">28.10.25</p>
        """,
        "lxml",
    )

    item = list(scraper.extract_items(soup))[0]

    assert item.title == "La Fundacio Pere Tarres reclama al Parlament mes inversio en educacio"
    assert item.url == "https://www.peretarres.org/actualitat/noticies/reclamem-al-parlament-mes-inversio-educacio"
    assert item.published_at == datetime(2025, 10, 28, tzinfo=timezone.utc)
