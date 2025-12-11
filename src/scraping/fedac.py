"""Scraper implementation for https://escoles.fedac.cat/noticies/."""
from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


_API_URL = (
    "https://escoles.fedac.cat/wp-json/wp/v2/posts?per_page=9"
    "&_fields=link,title.rendered,date,excerpt.rendered"
)


class FedacScraper(BaseScraper):
    site_id = "fedac"
    base_url = "https://escoles.fedac.cat"
    listing_url = "https://escoles.fedac.cat/noticies/"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:  # noqa: ARG002
        response = self._get(_API_URL)
        data = response.json()

        items: list[NewsItem] = []
        seen: set[str] = set()

        for entry in data:
            link = entry.get("link", "").strip()
            if not link:
                continue
            normalized = self._normalize_url(link)
            if normalized in seen:
                continue
            seen.add(normalized)

            title_html = entry.get("title", {}).get("rendered", "")
            title = _strip_html(title_html)
            if not title:
                continue

            excerpt_html = entry.get("excerpt", {}).get("rendered", "")
            summary = _strip_html(excerpt_html) or normalized

            published_at = _parse_iso(entry.get("date"))

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


def _strip_html(value: str) -> str:
    if not value:
        return ""
    text = BeautifulSoup(unescape(value), "lxml").get_text(" ", strip=True)
    return text


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = ["FedacScraper"]
