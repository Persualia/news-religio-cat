"""Scraper implementation for https://www.caminsfundacio.org/posat-al-dia/."""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from models import NewsItem, utcnow

from .base import BaseScraper


class CaminsFundacioScraper(BaseScraper):
    site_id = "caminsfundacio"
    base_url = "https://www.caminsfundacio.org"
    listing_url = "https://www.caminsfundacio.org/posat-al-dia/"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        for article in listing_soup.select("article.fusion-post-grid"):
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

            summary = _extract_summary(article) or normalized
            date_text = _extract_date_text(article)
            published_at = _parse_date(date_text)

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
    if not container:
        return ""
    paragraph = container.find("p")
    if paragraph is None:
        return container.get_text(" ", strip=True)
    return paragraph.get_text(" ", strip=True)


def _extract_date_text(article: Tag) -> str:
    meta = article.select_one(".fusion-single-line-meta")
    if not meta:
        return ""
    for span in meta.find_all("span", recursive=False):
        classes = set(span.get("class", []))
        if classes & {"updated", "vcard", "fusion-inline-sep"}:
            continue
        text = span.get_text(strip=True)
        if text:
            return text
    for string in meta.stripped_strings:
        return string
    return ""


_MONTHS = {
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
    "septembre": 9,
    "octubre": 10,
    "oct": 10,
    "novembre": 11,
    "nov": 11,
    "desembre": 12,
    "des": 12,
}


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = unicodedata.normalize("NFKD", value)
    cleaned = cleaned.replace(",", " ")
    parts = [part for part in cleaned.split() if part]
    if len(parts) < 3:
        return None

    # The listing shows month first (e.g., "novembre 21 2025").
    month_token = parts[0].lower()
    month = _MONTHS.get(month_token)
    if month is None:
        # Some locales show day first (e.g., "21 novembre 2025").
        try:
            day_candidate = int(parts[0])
        except ValueError:
            return None
        if len(parts) < 3:
            return None
        month = _MONTHS.get(parts[1].lower())
        if month is None:
            return None
        day = day_candidate
        year_index = 2
    else:
        try:
            day = int(parts[1])
        except ValueError:
            return None
        year_index = 2

    if len(parts) <= year_index:
        return None
    try:
        year = int(parts[year_index])
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


__all__ = ["CaminsFundacioScraper"]
