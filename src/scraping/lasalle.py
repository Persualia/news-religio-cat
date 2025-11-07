"""Scraper implementation for https://lasalle.cat/wp-json/wp/v2/posts."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class LaSalleScraper(BaseScraper):
    site_id = "lasalle"
    base_url = "https://lasalle.cat"
    listing_url = (
        "https://lasalle.cat/wp-json/wp/v2/posts"
        "?per_page=9&_fields=link,title.rendered,date"
    )
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        text = listing_soup.get_text(strip=True)
        if not text:
            return []

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []

        seen: set[str] = set()
        items: list[NewsItem] = []

        for entry in payload:
            href = (entry.get("link") or "").strip()
            if not href:
                continue

            normalized = self._normalize_url(href)
            if normalized in seen:
                continue
            seen.add(normalized)

            title_html = (entry.get("title", {}) or {}).get("rendered", "")
            title = _clean_text(title_html)
            if not title:
                continue

            published_at = _parse_datetime(entry.get("date"))
            metadata = {"base_url": self.base_url, "lang": self.default_lang}
            if published_at:
                metadata["published_at"] = _format_iso(published_at)

            items.append(
                NewsItem(
                    source=self.site_id,
                    title=title,
                    url=normalized,
                    summary=normalized,
                    published_at=published_at or utcnow(),
                    metadata=metadata,
                )
            )

        return items


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return BeautifulSoup(value, "html.parser").get_text(strip=True)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = ["LaSalleScraper"]
