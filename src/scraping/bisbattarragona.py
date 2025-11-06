"""Scraper implementation for https://www.arquebisbattarragona.cat/noticies/."""
from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class BisbatTarragonaScraper(BaseScraper):
    site_id = "bisbattarragona"
    base_url = "https://www.arquebisbattarragona.cat"
    listing_url = "https://www.arquebisbattarragona.cat/"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        seen: set[str] = set()
        items: list[NewsItem] = []

        articles = listing_soup.select(".et_pb_post") or listing_soup.select("article")
        use_simple_iteration = False
        if not articles:
            articles = [listing_soup]
            use_simple_iteration = True

        for article in articles:
            anchor = article.select_one("h2.entry-title a[href]") or article.select_one("a[href]")
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

            date_tag = article.select_one(".post-meta .published") or article.select_one("time")
            date_text = date_tag.get_text(" ", strip=True) if date_tag else ""
            published_at = _parse_date(date_text)

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

        if use_simple_iteration:
            for anchor in listing_soup.select("a[href]"):
                href = anchor.get("href", "").strip()
                if not href or href.startswith("#"):
                    continue
                normalized = self._normalize_url(href)
                if normalized in seen:
                    continue
                title = anchor.get_text(strip=True)
                if not title:
                    continue
                seen.add(normalized)
                metadata = {"base_url": self.base_url, "lang": self.default_lang}
                items.append(
                    NewsItem(
                        source=self.site_id,
                        title=title,
                        url=normalized,
                        summary=normalized,
                        published_at=utcnow(),
                        metadata=metadata,
                    )
                )

        return items


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


_MONTH_MAP: dict[str, int] = {
    "gen": 1,
    "gener": 1,
    "ene": 1,
    "jan": 1,
    "feb": 2,
    "febr": 2,
    "febrer": 2,
    "february": 2,
    "mar": 3,
    "marc": 3,
    "marzo": 3,
    "march": 3,
    "abr": 4,
    "abril": 4,
    "apr": 4,
    "april": 4,
    "maig": 5,
    "mai": 5,
    "may": 5,
    "jun": 6,
    "juny": 6,
    "junio": 6,
    "june": 6,
    "jul": 7,
    "juliol": 7,
    "julio": 7,
    "july": 7,
    "ago": 8,
    "ag": 8,
    "agost": 8,
    "aug": 8,
    "august": 8,
    "set": 9,
    "sept": 9,
    "setembre": 9,
    "septiembre": 9,
    "september": 9,
    "oct": 10,
    "octubre": 10,
    "october": 10,
    "nov": 11,
    "novembre": 11,
    "november": 11,
    "des": 12,
    "desembre": 12,
    "diciembre": 12,
    "dec": 12,
    "december": 12,
}


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.replace("\u2019", "'")
    normalized = normalized.replace("\u00a0", " ")
    normalized = normalized.lower()
    normalized = normalized.replace(",", " ")
    normalized = normalized.replace(".", " ")
    normalized = normalized.replace("º", " ")
    normalized = normalized.replace("ª", " ")
    normalized = normalized.replace("er ", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.strip()
    if not normalized:
        return None

    tokens = normalized.split()

    year: int | None = None
    for token in reversed(tokens):
        if token.isdigit() and len(token) == 4:
            year = int(token)
            break
    if year is None:
        return None

    month_token: str | None = None
    day_token: str | None = None
    for token in tokens:
        if token == "de" or token == "del":
            continue
        if token.isdigit():
            if day_token is None and len(token) <= 2:
                day_token = token
            continue
        if token == str(year):
            continue
        if month_token is None:
            month_token = token

    if day_token is None or month_token is None:
        return None

    key = month_token
    key = key.strip()
    key = key.replace("'", "")
    key = key.replace("-", "")
    key = unicodedata.normalize("NFKD", key)
    key = key.encode("ascii", "ignore").decode("ascii")
    key = key.lower()

    month = _MONTH_MAP.get(key)
    if month is None:
        return None

    try:
        day = int(day_token)
    except ValueError:
        return None

    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


__all__ = ["BisbatTarragonaScraper"]
