"""Scraper implementations for news ingestion."""
from __future__ import annotations

from typing import Iterable, Sequence, Type

from .base import BaseScraper
from .bisbatlleida import BisbatLleidaScraper
from .bisbatsolsona import BisbatSolsonaScraper
from .bisbaturgell import BisbatUrgellScraper
from .claretians import ClaretiansScraper
from .escolapia import EscolaPiaScraper
from .jesuites import JesuitesScraper
from .lasalle import LaSalleScraper
from .maristes import MaristesScraper
from .salesians import SalesiansScraper

_SCRAPER_REGISTRY: dict[str, Type[BaseScraper]] = {
    BisbatLleidaScraper.site_id: BisbatLleidaScraper,
    BisbatSolsonaScraper.site_id: BisbatSolsonaScraper,
    BisbatUrgellScraper.site_id: BisbatUrgellScraper,
    ClaretiansScraper.site_id: ClaretiansScraper,
    EscolaPiaScraper.site_id: EscolaPiaScraper,
    JesuitesScraper.site_id: JesuitesScraper,
    LaSalleScraper.site_id: LaSalleScraper,
    MaristesScraper.site_id: MaristesScraper,
    SalesiansScraper.site_id: SalesiansScraper,
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
    "BisbatSolsonaScraper",
    "BisbatUrgellScraper",
    "ClaretiansScraper",
    "EscolaPiaScraper",
    "JesuitesScraper",
    "LaSalleScraper",
    "MaristesScraper",
    "SalesiansScraper",
    "get_scraper_classes",
    "instantiate_scrapers",
    "list_scraper_ids",
]
