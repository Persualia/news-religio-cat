"""Scraper implementation for https://comtal.org/es/noticias/."""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from models import NewsItem, utcnow

from .base import BaseScraper


class FundacioComtalScraper(BaseScraper):
    site_id = "fundaciocomtal"
    base_url = "https://comtal.org"
    listing_url = "https://comtal.org/es/noticias/"
    default_lang = "es"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        for card in listing_soup.select(".latest-blog .blog-item"):
            anchor = card.select_one("a[href]")
            if not anchor:
                continue

            href = anchor.get("href", "").strip()
            if not href:
                continue

            normalized = self._normalize_url(href)
            if normalized in seen:
                continue
            seen.add(normalized)

            title_tag = card.select_one("h4")
            title = title_tag.get_text(strip=True) if title_tag else anchor.get("title", "").strip()
            if not title:
                continue

            summary = normalized
            date_text = _extract_date_text(card)
            published_at = _parse_date(date_text) if date_text else None

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


def _extract_date_text(card: Tag) -> str:
    date_span = card.select_one(".blog-item-description span")
    if not date_span:
        return ""
    return date_span.get_text(strip=True)


_MONTH_MAP = {
    "enero": 1,
    "ene": 1,
    "febrero": 2,
    "feb": 2,
    "marzo": 3,
    "mar": 3,
    "abril": 4,
    "abr": 4,
    "mayo": 5,
    "may": 5,
    "junio": 6,
    "jun": 6,
    "julio": 7,
    "jul": 7,
    "agosto": 8,
    "ago": 8,
    "septiembre": 9,
    "setiembre": 9,
    "sep": 9,
    "octubre": 10,
    "oct": 10,
    "noviembre": 11,
    "nov": 11,
    "diciembre": 12,
    "dic": 12,
}


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = unicodedata.normalize("NFKD", value)
    parts = [part for part in normalized.replace(",", " ").split() if part]
    if len(parts) < 3:
        return None

    try:
        day = int(parts[0])
    except ValueError:
        return None

    month_token = parts[1].strip().lower()
    month = _MONTH_MAP.get(month_token)
    if not month:
        return None

    try:
        year = int(parts[2])
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


__all__ = ["FundacioComtalScraper"]
