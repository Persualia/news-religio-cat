"""Shared scraping infrastructure returning lightweight news items."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Iterable, List, Optional
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

import httpx
from bs4 import BeautifulSoup

from config import get_settings
from models import NewsItem


MAX_ITEMS_PER_SOURCE = 9


class ScraperNoArticlesError(RuntimeError):
    """Raised when a scraper yields zero URLs from the listing page."""

    def __init__(self, site_id: str) -> None:
        super().__init__(f"No articles discovered for site '{site_id}'")
        self.site_id = site_id


class BaseScraper(ABC):
    """Reusable base scraper handling HTTP concerns and orchestration."""

    site_id: str
    base_url: str
    listing_url: str
    default_lang: str = "ca"

    def __init__(self) -> None:
        settings = get_settings().scraper
        self._client = httpx.Client(
            headers={"User-Agent": settings.user_agent},
            timeout=settings.request_timeout,
            follow_redirects=True,
        )
        self._throttle_seconds = settings.throttle_seconds
        self._max_retries = settings.max_retries

    # -- Template methods -------------------------------------------------

    @abstractmethod
    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        """Return the news items found in the listing soup."""

    # -- Orchestration ----------------------------------------------------

    def scrape(self, *, limit: Optional[int] = None) -> List[NewsItem]:
        listing_soup = self._get_soup(self.listing_url)
        items = list(self.extract_items(listing_soup))
        if not items:
            raise ScraperNoArticlesError(self.site_id)
        effective_limit = MAX_ITEMS_PER_SOURCE
        if limit is not None:
            effective_limit = min(limit, MAX_ITEMS_PER_SOURCE)
        items = items[:effective_limit]
        return items

    # -- Networking helpers ----------------------------------------------

    def _get(self, url: str) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.get(url)
                response.raise_for_status()
                return response
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                sleep_time = self._throttle_seconds * attempt if self._throttle_seconds else attempt
                time.sleep(sleep_time)
        if last_exc:
            raise last_exc
        raise RuntimeError(f"Failed to GET {url}")

    def _get_soup(self, url: str) -> BeautifulSoup:
        response = self._get(url)
        return BeautifulSoup(response.text, "lxml")

    def _normalize_url(self, url: str) -> str:
        absolute = urljoin(self.base_url, url)
        try:
            split = urlsplit(absolute)
            scheme = split.scheme or "https"
            netloc = (split.netloc or "").lower()
            if netloc.endswith(":80") and scheme == "http":
                netloc = netloc[:-3]
            if netloc.endswith(":443") and scheme == "https":
                netloc = netloc[:-4]

            path = split.path or "/"
            while "//" in path:
                path = path.replace("//", "/")
            if path != "/" and path.endswith("/"):
                path = path[:-1]

            params = []
            for key, value in parse_qsl(split.query, keep_blank_values=False):
                lowered = key.lower()
                if lowered.startswith("utm_"):
                    continue
                if lowered in {"fbclid", "gclid", "yclid", "mc_cid", "mc_eid", "ref", "ref_src", "igshid"}:
                    continue
                params.append((key, value))
            params.sort()
            query = urlencode(params, doseq=True)

            return urlunsplit((scheme, netloc, path, query, ""))
        except Exception:  # noqa: BLE001
            return absolute


__all__ = ["BaseScraper", "ScraperNoArticlesError"]
