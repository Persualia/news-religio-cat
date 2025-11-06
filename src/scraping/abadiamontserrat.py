"""Scraper implementation for https://www.millenarimontserrat.cat/noticies."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from models import NewsItem, utcnow

from .base import BaseScraper


class AbadiaMontserratScraper(BaseScraper):
    site_id = "abadiamontserrat"
    base_url = "https://www.millenarimontserrat.cat"
    listing_url = "https://www.millenarimontserrat.cat/noticies"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        entries = listing_soup.select(".llistats_noticia .noticia-level-4")
        if not entries:
            entries = listing_soup.select(".noticia-level-4")

        items: list[NewsItem] = []
        seen: set[str] = set()

        for entry in entries:
            anchor = entry.select_one(".titolnoticiallistat a[href]")
            if anchor is None:
                continue

            href = anchor.get("href", "").strip()
            if not href:
                continue

            normalized = self._normalize_url(href)
            if normalized in seen:
                continue
            seen.add(normalized)

            title = anchor.get_text(strip=True)
            if not title:
                continue

            date_tag = entry.select_one(".quan-fa")
            published_at = _parse_date(date_tag.get_text(strip=True) if date_tag else "")

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


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            parsed = datetime.strptime(cleaned, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = ["AbadiaMontserratScraper"]
