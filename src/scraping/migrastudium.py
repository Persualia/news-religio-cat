"""Scraper implementation for https://www.migrastudium.org/actualitat."""
from __future__ import annotations

import logging
import unicodedata
from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from models import NewsItem, utcnow

from .base import BaseScraper

logger = logging.getLogger(__name__)


class MigrastudiumScraper(BaseScraper):
    site_id = "migrastudium"
    base_url = "https://www.migrastudium.org"
    listing_url = "https://www.migrastudium.org/actualitat"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        for article in listing_soup.select("article.post"):
            anchor = article.select_one(".post-title a[href]")
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

            summary = _extract_summary(article)
            published_at = self._extract_listing_date(article)
            if published_at is None:
                published_at = self._fetch_published_at(normalized)

            metadata = {"base_url": self.base_url, "lang": self.default_lang}
            if published_at:
                metadata["published_at"] = _format_iso(published_at)

            items.append(
                NewsItem(
                    source=self.site_id,
                    title=title,
                    url=normalized,
                    summary=summary or normalized,
                    published_at=published_at or utcnow(),
                    metadata=metadata,
                )
            )

        return items

    def _extract_listing_date(self, article: Tag) -> datetime | None:
        date_container = article.select_one(".post-date")
        if not date_container:
            return None
        parsed = _parse_date_string(date_container.get_text(" ", strip=True))
        return parsed

    def _fetch_published_at(self, article_url: str) -> datetime | None:
        try:
            detail_soup = self._get_soup(article_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch Migrastudium article %s: %s", article_url, exc)
            return None
        date_node = detail_soup.select_one(".field--name-node-post-date")
        if not date_node:
            return None
        parsed = _parse_date_string(date_node.get_text(" ", strip=True))
        if parsed is None:
            logger.debug("Unable to parse detail date for %s: %s", article_url, date_node)
        return parsed


_MONTH_MAP = {
    "gen": 1,
    "gener": 1,
    "enero": 1,
    "ene": 1,
    "feb": 2,
    "febr": 2,
    "febrer": 2,
    "febrero": 2,
    "mar": 3,
    "marc": 3,
    "març": 3,
    "marzo": 3,
    "abr": 4,
    "abril": 4,
    "apr": 4,
    "mai": 5,
    "maig": 5,
    "mayo": 5,
    "may": 5,
    "jun": 6,
    "juny": 6,
    "junio": 6,
    "jul": 7,
    "juliol": 7,
    "julio": 7,
    "ago": 8,
    "ag": 8,
    "agost": 8,
    "agosto": 8,
    "set": 9,
    "setembre": 9,
    "sept": 9,
    "septiembre": 9,
    "sep": 9,
    "oct": 10,
    "octubre": 10,
    "nov": 11,
    "novembre": 11,
    "noviembre": 11,
    "des": 12,
    "desembre": 12,
    "diciembre": 12,
    "dec": 12,
}


def _month_to_number(value: str) -> int | None:
    cleaned = _normalize_token(value)
    if not cleaned:
        return None
    return _MONTH_MAP.get(cleaned)


def _normalize_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    letters = [ch for ch in normalized.lower() if ch.isalpha()]
    return "".join(letters)


def _extract_summary(article: Tag) -> str:
    body_field = article.select_one(".post-body .field")
    if body_field is None:
        return ""
    return body_field.get_text(" ", strip=True)


def _parse_date_string(value: str) -> datetime | None:
    if not value:
        return None
    normalized = unicodedata.normalize("NFKD", value)
    tokens: list[str] = []
    for raw in normalized.replace(",", " ").replace("/", " ").split():
        token = raw.strip()
        if not token:
            continue
        lowered = token.lower().strip(".,")
        if lowered in {"de", "del"}:
            continue
        tokens.append(token)

    day = None
    month = None
    year = None
    for token in tokens:
        digits = "".join(ch for ch in token if ch.isdigit())
        if digits:
            number = int(digits)
            if number > 31:
                year = number
            elif day is None:
                day = number
            continue
        month_candidate = _month_to_number(token)
        if month_candidate:
            month = month_candidate

    if day and month and year:
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = ["MigrastudiumScraper"]
