"""Scraper implementation for https://caputxins.cat/actualitat-caputxina/."""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from models import NewsItem, utcnow

from .base import BaseScraper


class FranciscansScraper(BaseScraper):
    site_id = "franciscans"
    base_url = "https://caputxins.cat"
    listing_url = "https://caputxins.cat/actualitat-caputxina/"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        for article in listing_soup.select("article.fusion-post-grid"):
            link = article.select_one(".fusion-rollover-link")
            if link is None:
                continue
            href = link.get("href", "").strip()
            if not href:
                continue

            normalized = self._normalize_url(href)
            if normalized in seen:
                continue
            seen.add(normalized)

            title_tag = article.select_one(".entry-title")
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title:
                continue

            date_text = _extract_date(article)
            published_at = _parse_catalan_date(date_text) if date_text else None

            summary = _extract_summary(article) or normalized

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


def _extract_summary(article: Tag) -> str:
    container = article.select_one(".fusion-post-content-container")
    if container is None:
        return ""
    return container.get_text(" ", strip=True)


def _extract_date(article: Tag) -> str:
    meta = article.select_one(".fusion-single-line-meta")
    if meta is None:
        return ""
    for span in meta.find_all("span", recursive=False):
        classes = set(span.get("class", []))
        if classes & {"vcard", "updated", "fusion-inline-sep"}:
            continue
        text = span.get_text(strip=True)
        if text:
            return text
    for string in meta.stripped_strings:
        return string
    return ""


_MONTH_MAP = {
    "gener": 1,
    "gen": 1,
    "febrer": 2,
    "feb": 2,
    "marc": 3,
    "març": 3,
    "mar": 3,
    "abril": 4,
    "abr": 4,
    "maig": 5,
    "mai": 5,
    "juny": 6,
    "jun": 6,
    "juliol": 7,
    "jul": 7,
    "agost": 8,
    "ago": 8,
    "setembre": 9,
    "set": 9,
    "octubre": 10,
    "oct": 10,
    "novembre": 11,
    "nov": 11,
    "desembre": 12,
    "des": 12,
}


def _parse_catalan_date(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = unicodedata.normalize("NFKD", value)
    cleaned = cleaned.replace(",", " ")
    parts = [part for part in cleaned.split() if part]
    if len(parts) < 3:
        return None

    # Accept formats "9 de desembre de 2025" or "desembre 9, 2025".
    if parts[0].isdigit():
        day_index = 0
        month_index = 2 if parts[1].lower() == "de" else 1
    else:
        month_index = 0
        day_index = 1
    try:
        day = int(parts[day_index])
    except ValueError:
        return None

    month_token = parts[month_index].lower()
    month = _MONTH_MAP.get(month_token)
    if month is None:
        return None

    year_candidates = [part for part in parts if part.isdigit() and len(part) == 4]
    if not year_candidates:
        return None
    year = int(year_candidates[-1])

    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = ["FranciscansScraper"]
