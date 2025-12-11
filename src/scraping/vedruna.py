"""Scraper implementation for https://vedruna.cat/noticies/."""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class VedrunaScraper(BaseScraper):
    site_id = "vedruna"
    base_url = "https://vedruna.cat"
    listing_url = "https://vedruna.cat/noticies/"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        for node in listing_soup.select("article.elementor-post"):
            anchor = node.select_one(".elementor-post__title a[href]")
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

            summary_tag = node.select_one(".elementor-post__excerpt")
            summary = summary_tag.get_text(" ", strip=True) if summary_tag else normalized

            date_text = node.select_one(".elementor-post__meta-data")
            published_at = _parse_catalan_date(date_text.get_text(" ", strip=True) if date_text else "")

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
    "gener": 1,
    "febrer": 2,
    "marc": 3,
    "març": 3,
    "abril": 4,
    "maig": 5,
    "juny": 6,
    "juliol": 7,
    "agost": 8,
    "setembre": 9,
    "octubre": 10,
    "novembre": 11,
    "desembre": 12,
}


def _parse_catalan_date(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = unicodedata.normalize("NFKD", value)
    parts = [part for part in cleaned.replace(",", " ").split() if part]
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


__all__ = ["VedrunaScraper"]
