"""Scraper implementation for https://ajuntament.barcelona.cat/oficina-afers-religiosos/."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class OARScraper(BaseScraper):
    site_id = "oar"
    base_url = "https://ajuntament.barcelona.cat"
    listing_url = "https://ajuntament.barcelona.cat/oficina-afers-religiosos/ca/noticies"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        api_url = _extract_api_url(listing_soup, self.base_url)
        if not api_url:
            return []

        data = self._fetch_api_response(api_url)
        news_entries = data.get("news") or []

        items: list[NewsItem] = []
        seen: set[str] = set()

        for entry in news_entries:
            detail = entry.get("detall")
            if not detail:
                continue
            normalized = self._normalize_url(urljoin(self.base_url, detail))
            if normalized in seen:
                continue
            seen.add(normalized)

            title = (entry.get("titol") or "").strip()
            if not title:
                continue

            summary = (entry.get("cos") or "").strip() or title
            published_at = _parse_published_at(entry.get("data"))

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

    def _fetch_api_response(self, api_url: str) -> dict[str, Any]:
        response = self._get(api_url)
        return response.json()


def _extract_api_url(listing_soup: BeautifulSoup, base_url: str) -> str:
    button = listing_soup.select_one("#ajuntament-actualitat-filtrar[data-api]")
    if button is None:
        button = listing_soup.select_one("[data-api]")
    if button is None:
        return ""
    relative = button.get("data-api", "").strip()
    if not relative:
        return ""
    return urljoin(base_url, relative)


_DATE_RE = re.compile(
    r"(?P<day>\d{1,2})/(?P<month>\d{1,2})/(?P<year>\d{4})(?:\s*-\s*(?P<hour>\d{1,2}):(?P<minute>\d{2}))?",
    re.UNICODE,
)


def _parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    match = _DATE_RE.search(value)
    if not match:
        return None
    day = int(match.group("day"))
    month = int(match.group("month"))
    year = int(match.group("year"))
    hour = int(match.group("hour") or 0)
    minute = int(match.group("minute") or 0)
    try:
        return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    except ValueError:
        return None


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = ["OARScraper"]
