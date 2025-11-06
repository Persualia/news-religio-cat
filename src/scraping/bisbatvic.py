"""Scraper implementation for https://www.bisbatvic.org/ca/noticies."""
from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from models import NewsItem, utcnow

from .base import BaseScraper


class BisbatVicScraper(BaseScraper):
    site_id = "bisbatvic"
    base_url = "https://www.bisbatvic.org"
    listing_url = "https://www.bisbatvic.org/ca/noticies?field_tax_blog_tid=All"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        rows = listing_soup.select(".view-content .views-row")
        if not rows:
            rows = listing_soup.select(".node-article")

        items: list[NewsItem] = []
        seen: set[str] = set()

        for row in rows:
            node = row.select_one(".node-article") if isinstance(row, Tag) else None
            container = node or row

            href = _extract_href(container)
            if not href:
                continue

            normalized = self._normalize_url(href)
            if normalized in seen:
                continue
            seen.add(normalized)

            title_node = container.select_one(".field-name-title .title") or container.select_one(".title")
            title = title_node.get_text(strip=True) if title_node else ""
            if not title:
                continue

            date_node = container.select_one(".data")
            published_at = _parse_date(date_node.get_text(" ", strip=True) if date_node else "")

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


def _extract_href(node: Tag | None) -> str | None:
    if node is None:
        return None
    onclick = node.get("onclick")
    if onclick:
        match = re.search(r"location\.href=['\"]([^'\"]+)['\"]", onclick)
        if match:
            return match.group(1)
    about = node.get("about")
    if about:
        return about
    anchor = node.select_one("a[href]")
    if anchor:
        return anchor.get("href")
    return None


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


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = unicodedata.normalize("NFKD", value)
    cleaned = cleaned.replace("\u00a0", " ")
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    parts = cleaned.split()
    if len(parts) < 3:
        return None
    day_part, month_part, year_part = parts[0], parts[1], parts[-1]
    try:
        day = int(day_part)
    except ValueError:
        return None
    month_key = month_part.lower()
    month_key = month_key.replace(".", "")
    month_key = month_key.replace("ç", "c")
    month = _MONTHS.get(month_key)
    if month is None:
        return None
    try:
        year = int(year_part)
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


__all__ = ["BisbatVicScraper"]
