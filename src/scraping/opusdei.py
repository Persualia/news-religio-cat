"""Scraper implementation for https://opusdei.org/ca-es/."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class OpusDeiScraper(BaseScraper):
    site_id = "opusdei"
    base_url = "https://opusdei.org"
    listing_url = "https://opusdei.org/ca-es/lastarticles.xml"
    default_lang = "ca"

    def _get_soup(self, url: str) -> BeautifulSoup:
        response = self._get(url)
        return BeautifulSoup(response.text, "xml")

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        for entry in listing_soup.select("entry"):
            link_tag = entry.select_one("link[rel='alternate']")
            link = link_tag.get("href", "").strip() if link_tag else ""
            if not link:
                continue

            normalized = self._normalize_url(link)
            if normalized in seen:
                continue
            seen.add(normalized)

            title = entry.select_one("title")
            title_text = title.get_text(strip=True) if title else ""
            if not title_text:
                continue

            summary = ""
            summary_tag = entry.select_one("summary")
            if summary_tag and summary_tag.string:
                summary = summary_tag.get_text(" ", strip=True)
            if not summary:
                summary = normalized

            updated = entry.select_one("updated")
            published_at = _parse_updated(updated.get_text(strip=True) if updated else None)

            metadata = {"base_url": self.base_url, "lang": self.default_lang}
            if published_at:
                metadata["published_at"] = _format_iso(published_at)

            items.append(
                NewsItem(
                    source=self.site_id,
                    title=title_text,
                    url=normalized,
                    summary=summary,
                    published_at=published_at or utcnow(),
                    metadata=metadata,
                )
            )

        return items


def _parse_updated(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = ["OpusDeiScraper"]
