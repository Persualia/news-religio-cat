"""Scraper implementations for news ingestion."""
from __future__ import annotations

from typing import Iterable, Sequence, Type

from .base import BaseScraper
from .jesuites import JesuitesScraper
from .maristes import MaristesScraper
from .lasalle import LaSalleScraper
from .escolapia import EscolaPiaScraper
from .salesians import SalesiansScraper
from .claretians import ClaretiansScraper
from .bisbatsolsona import BisbatSolsonaScraper
from .bisbaturgell import BisbatUrgellScraper
from .bisbatlleida import BisbatLleidaScraper
from .bisbattarragona import BisbatTarragonaScraper
from .bisbatgirona import BisbatGironaScraper
from .bisbatbarcelona import BisbatBarcelonaScraper
from .bisbatsantfeliu import BisbatSantFeliuScraper
from .bisbatterrassa import BisbatTerrassaScraper
from .bisbatvic import BisbatVicScraper
from .bisbattortosa import BisbatTortosaScraper
from .sagradafamilia import SagradaFamiliaScraper
from .santjoandedeu import SantJoanDeDeuScraper
from .abadiamontserrat import AbadiaMontserratScraper
from .peretarres import PeretarresScraper
from .serveijesuitarefugiats import ServeiJesuitaRefugiatsScraper
from .migrastudium import MigrastudiumScraper
from .fundaciocomtal import FundacioComtalScraper
from .caminsfundacio import CaminsFundacioScraper

# Order matters: earlier entries receive higher priority when sorting mixed results.
_SCRAPER_REGISTRY: dict[str, Type[BaseScraper]] = {
    JesuitesScraper.site_id: JesuitesScraper,
    MaristesScraper.site_id: MaristesScraper,
    LaSalleScraper.site_id: LaSalleScraper,
    EscolaPiaScraper.site_id: EscolaPiaScraper,
    SalesiansScraper.site_id: SalesiansScraper,
    ClaretiansScraper.site_id: ClaretiansScraper,
    BisbatSolsonaScraper.site_id: BisbatSolsonaScraper,
    BisbatUrgellScraper.site_id: BisbatUrgellScraper,
    BisbatLleidaScraper.site_id: BisbatLleidaScraper,
    BisbatTarragonaScraper.site_id: BisbatTarragonaScraper,
    BisbatGironaScraper.site_id: BisbatGironaScraper,
    BisbatBarcelonaScraper.site_id: BisbatBarcelonaScraper,
    BisbatSantFeliuScraper.site_id: BisbatSantFeliuScraper,
    BisbatTerrassaScraper.site_id: BisbatTerrassaScraper,
    BisbatVicScraper.site_id: BisbatVicScraper,
    BisbatTortosaScraper.site_id: BisbatTortosaScraper,
    SagradaFamiliaScraper.site_id: SagradaFamiliaScraper,
    SantJoanDeDeuScraper.site_id: SantJoanDeDeuScraper,
    AbadiaMontserratScraper.site_id: AbadiaMontserratScraper,
    PeretarresScraper.site_id: PeretarresScraper,
    ServeiJesuitaRefugiatsScraper.site_id: ServeiJesuitaRefugiatsScraper,
    MigrastudiumScraper.site_id: MigrastudiumScraper,
    FundacioComtalScraper.site_id: FundacioComtalScraper,
    CaminsFundacioScraper.site_id: CaminsFundacioScraper,
}

SCRAPER_PRIORITY: dict[str, int] = {
    site_id: index for index, site_id in enumerate(_SCRAPER_REGISTRY)
}


def list_scraper_ids() -> list[str]:
    """Return all available scraper identifiers."""

    return list(_SCRAPER_REGISTRY.keys())


def get_scraper_classes(site_ids: Sequence[str] | None = None) -> Iterable[Type[BaseScraper]]:
    """Yield scraper classes for the requested ``site_ids``.

    Args:
        site_ids: Optional list of site identifiers. When ``None`` all
            registered scrapers are returned.

    Raises:
        ValueError: If one or more identifiers are unknown.
    """

    if site_ids is None:
        return _SCRAPER_REGISTRY.values()

    unknown = [site_id for site_id in site_ids if site_id not in _SCRAPER_REGISTRY]
    if unknown:
        joined = ", ".join(sorted(unknown))
        raise ValueError(f"Unknown scraper site_id(s): {joined}")

    return (_SCRAPER_REGISTRY[site_id] for site_id in site_ids)


def instantiate_scrapers(site_ids: Sequence[str] | None = None) -> list[BaseScraper]:
    """Instantiate scrapers for the requested ``site_ids``."""

    return [scraper_cls() for scraper_cls in get_scraper_classes(site_ids)]


__all__ = [
    "BaseScraper",
    "BisbatLleidaScraper",
    "BisbatTarragonaScraper",
    "BisbatGironaScraper",
    "BisbatBarcelonaScraper",
    "BisbatSantFeliuScraper",
    "BisbatTerrassaScraper",
    "BisbatVicScraper",
    "BisbatTortosaScraper",
    "SagradaFamiliaScraper",
    "SantJoanDeDeuScraper",
    "AbadiaMontserratScraper",
    "PeretarresScraper",
    "ServeiJesuitaRefugiatsScraper",
    "MigrastudiumScraper",
    "FundacioComtalScraper",
    "CaminsFundacioScraper",
    "BisbatSolsonaScraper",
    "BisbatUrgellScraper",
    "ClaretiansScraper",
    "EscolaPiaScraper",
    "JesuitesScraper",
    "LaSalleScraper",
    "MaristesScraper",
    "SalesiansScraper",
    "SCRAPER_PRIORITY",
    "get_scraper_classes",
    "instantiate_scrapers",
    "list_scraper_ids",
]
