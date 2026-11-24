"""Shared scraping infrastructure returning lightweight news items."""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Iterable, List, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from config import get_settings
from models import NewsItem

from .cloudflare import CloudflareRenderError, CloudflareRenderer


MAX_ITEMS_PER_SOURCE = 9

# Origin responses that usually mean "your IP is blocked or rate limited" and are
# worth retrying from Cloudflare's network.
_FALLBACK_STATUS_CODES = frozenset({403, 429, 503})

logger = logging.getLogger(__name__)


class ScraperNoArticlesError(RuntimeError):
    """Raised when a scraper yields zero URLs from the listing page."""

    def __init__(self, site_id: str) -> None:
        super().__init__(f"No articles discovered for site '{site_id}'")
        self.site_id = site_id


class ScraperBlockedError(RuntimeError):
    """Raised when an origin blocks automated scraping before content is returned."""

    def __init__(self, site_id: str, detail: str) -> None:
        super().__init__(detail)
        self.site_id = site_id
        self.detail = detail


class ScraperUnexpectedContentError(RuntimeError):
    """Raised when an origin returns a response the scraper cannot parse."""

    def __init__(self, site_id: str, detail: str) -> None:
        super().__init__(detail)
        self.site_id = site_id
        self.detail = detail


class BaseScraper(ABC):
    """Reusable base scraper handling HTTP concerns and orchestration."""

    site_id: str
    base_url: str
    listing_url: str
    default_lang: str = "ca"
    # Retry blocked requests through Cloudflare Browser Rendering when
    # CF_ACCOUNT_ID and CF_API_TOKEN are configured.
    cloudflare_fallback: bool = True

    def __init__(self) -> None:
        settings = get_settings().scraper
        self._client = httpx.Client(
            headers={"User-Agent": settings.user_agent},
            timeout=settings.request_timeout,
            follow_redirects=True,
        )
        self._request_timeout = settings.request_timeout
        self._throttle_seconds = settings.throttle_seconds
        self._max_retries = settings.max_retries
        self._cloudflare: Optional[CloudflareRenderer] = None
        if settings.cloudflare_account_id and settings.cloudflare_api_token:
            self._cloudflare = CloudflareRenderer(
                settings.cloudflare_account_id, settings.cloudflare_api_token
            )
        self._prefer_cloudflare = False
        # Direct-request errors that Cloudflare papered over, keyed by URL. If the
        # page Cloudflare returned turns out to be useless (e.g. a maintenance page
        # behind a real 503), the original error is the more accurate report.
        self._fallback_errors: dict[str, Exception] = {}

    # -- Template methods -------------------------------------------------

    @abstractmethod
    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        """Return the news items found in the listing soup."""

    # -- Orchestration ----------------------------------------------------

    def scrape(self, *, limit: Optional[int] = None) -> List[NewsItem]:
        listing_soup = self._get_soup(self.listing_url)
        items = list(self.extract_items(listing_soup))
        if not items:
            original_error = self._fallback_errors.get(self.listing_url)
            if original_error is not None:
                raise original_error
            raise ScraperNoArticlesError(self.site_id)
        effective_limit = MAX_ITEMS_PER_SOURCE
        if limit is not None:
            effective_limit = min(limit, MAX_ITEMS_PER_SOURCE)
        items = items[:effective_limit]
        return items

    # -- Networking helpers ----------------------------------------------

    def _get(self, url: str) -> httpx.Response:
        """GET ``url``, falling back to Cloudflare Browser Rendering if the origin blocks us.

        Once the fallback succeeds for a scraper, later requests from the same
        scraper go to Cloudflare first: an origin that blocked the listing will
        usually block the detail pages too.
        """
        if self._prefer_cloudflare:
            response = self._get_via_cloudflare(url)
            if response is not None:
                return response
        try:
            return self._get_direct(url)
        except Exception as exc:  # noqa: BLE001
            if not self._cloudflare_fallback_applies(exc):
                raise
            response = self._get_via_cloudflare(url)
            if response is None:
                raise
            self._prefer_cloudflare = True
            self._fallback_errors[url] = exc
            return response

    def _get_direct(self, url: str) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.get(url)
                response.raise_for_status()
                block_detail = self._detect_block(url, response)
                if block_detail:
                    raise ScraperBlockedError(getattr(self, "site_id", "<unknown>"), block_detail)
                return response
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response else "unknown"
                reason = getattr(exc.response, "reason_phrase", "") if exc.response else ""
                snippet = ""
                if exc.response is not None:
                    content = exc.response.text
                    if content:
                        snippet = content[:200].replace("\n", " ").strip()
                logger.warning(
                    "Scraper '%s' blocked with HTTP %s %s when requesting %s (attempt %d/%d). Body preview: %s",
                    getattr(self, "site_id", "<unknown>"),
                    status,
                    reason,
                    url,
                    attempt,
                    self._max_retries,
                    snippet,
                )
                last_exc = exc
                sleep_time = self._throttle_seconds * attempt if self._throttle_seconds else attempt
                time.sleep(sleep_time)
            except ScraperBlockedError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                sleep_time = self._throttle_seconds * attempt if self._throttle_seconds else attempt
                time.sleep(sleep_time)
        if last_exc:
            raise last_exc
        raise RuntimeError(f"Failed to GET {url}")

    def _detect_block(self, url: str, response: httpx.Response) -> Optional[str]:  # noqa: ARG002
        """Return a description if a 2xx ``response`` is really a bot block, else ``None``.

        Subclasses override this for origins whose challenges come back as 200.
        """
        waf_action = response.headers.get("x-amzn-waf-action")
        if waf_action:
            return f"AWS WAF returned action '{waf_action}' for {url}"
        return None

    # -- Cloudflare Browser Rendering fallback ----------------------------

    def _cloudflare_fallback_applies(self, exc: Exception) -> bool:
        if not self.cloudflare_fallback or self._cloudflare is None:
            return False
        if isinstance(exc, ScraperBlockedError):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response is not None and exc.response.status_code in _FALLBACK_STATUS_CODES
        # Timeouts and dropped connections are a common way of blocking IP ranges.
        # Other connection errors (DNS, TLS certificates, refused) are not blocks.
        return isinstance(exc, (httpx.TimeoutException, httpx.ReadError, httpx.RemoteProtocolError))

    def _get_via_cloudflare(self, url: str) -> Optional[httpx.Response]:
        site_id = getattr(self, "site_id", "<unknown>")
        if self._cloudflare is None:
            return None
        try:
            response = self._cloudflare.fetch(url)
        except CloudflareRenderError as exc:
            logger.warning("Scraper '%s': Cloudflare fallback failed for %s: %s", site_id, url, exc)
            return None
        block_detail = self._detect_block(url, response)
        if block_detail:
            logger.warning("Scraper '%s': still blocked via Cloudflare: %s", site_id, block_detail)
            return None
        logger.info("Scraper '%s': fetched %s via Cloudflare Browser Rendering", site_id, url)
        return response

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


__all__ = [
    "BaseScraper",
    "ScraperBlockedError",
    "ScraperNoArticlesError",
    "ScraperUnexpectedContentError",
]
