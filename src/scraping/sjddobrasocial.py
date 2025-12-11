"""Scraper implementation for https://solidaritat.santjoandedeu.org/actual/."""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class SJDDObraSocialScraper(BaseScraper):
    site_id = "sjddobrasocial"
    base_url = "https://solidaritat.santjoandedeu.org"
    listing_url = "https://solidaritat.santjoandedeu.org/actual/"
    default_lang = "es"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        for article in listing_soup.select("article.post"):
            anchor = article.select_one(".entry-title a[href]")
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

            summary_node = article.select_one(".entry-content")
            summary = summary_node.get_text(" ", strip=True) if summary_node else normalized

            date_node = article.select_one(".posted-on")
            published_at = _parse_spanish_date(date_node.get_text(" ", strip=True) if date_node else "")

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


_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def _parse_spanish_date(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = unicodedata.normalize("NFKD", value)
    cleaned = cleaned.replace(",", " ")
    parts = [part for part in cleaned.split() if part]
    if len(parts) < 4:
        return None
    try:
        day = int(parts[0])
    except ValueError:
        return None
    month = _MONTHS.get(parts[2].lower())
    if month is None:
        return None
    try:
        year = int(parts[-1])
    except ValueError:
        return None
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = ["SJDDObraSocialScraper"]
