"""Scraper implementation for https://lasalle.cat/feed/."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable, Optional

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper

logger = logging.getLogger(__name__)

_CF_HEADERS = {
    "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ca-ES,ca;q=0.9,en-US;q=0.8,en;q=0.7",
}


class LaSalleScraper(BaseScraper):
    site_id = "lasalle"
    base_url = "https://lasalle.cat"
    listing_url = "https://lasalle.cat/feed/"
    default_lang = "ca"

    def __init__(self) -> None:
        super().__init__()
        self._cf_scraper = self._init_cloudscraper()

    def _init_cloudscraper(self) -> Optional["cloudscraper.CloudScraper"]:
        try:
            import cloudscraper
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cloudscraper not available; falling back to default client: %s", exc)
            return None

        return cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )

    def _download_feed(self, url: str) -> str:
        if self._cf_scraper is None:
            response = self._get(url)
            return response.text

        try:
            response = self._cf_scraper.get(url, headers=_CF_HEADERS, timeout=self._request_timeout)
            response.raise_for_status()
            return response.text
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cloudscraper fetch failed (%s). Retrying with default client.", exc)
            response = self._get(url)
            return response.text

    def _get_soup(self, url: str) -> BeautifulSoup:
        text = self._download_feed(url)
        return BeautifulSoup(text, "xml")

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        for entry in listing_soup.select("item"):
            link_text = _extract_text(entry.select_one("link"))
            if not link_text:
                continue

            normalized = self._normalize_url(link_text)
            if normalized in seen:
                continue
            seen.add(normalized)

            title = _extract_text(entry.select_one("title"))
            if not title:
                continue

            summary = _extract_text(entry.select_one("description")) or normalized
            published_at = _parse_datetime(_extract_text(entry.select_one("pubDate")))

            metadata = {"base_url": self.base_url, "lang": self.default_lang}
            if published_at:
                metadata["published_at"] = _format_iso(published_at)

            items.append(
                NewsItem(
                    source=self.site_id,
                    title=title,
                    url=normalized,
                    summary=summary,
                    published_at=published_at or utcnow(),
                    metadata=metadata,
                )
            )

        return items


def _extract_text(node: BeautifulSoup | None) -> str:
    if node is None:
        return ""
    return node.get_text(strip=True)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = ["LaSalleScraper"]
