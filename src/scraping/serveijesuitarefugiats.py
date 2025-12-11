"""Scraper implementation for https://jrs.net/es/noticias-e-historias/."""
from __future__ import annotations

from datetime import datetime, timezone
import unicodedata
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class ServeiJesuitaRefugiatsScraper(BaseScraper):
    site_id = "serveijesuitarefugiats"
    base_url = "https://jrs.net"
    listing_url = "https://jrs.net/es/noticias-e-historias/"
    default_lang = "es"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        for card in listing_soup.select(".card-listing .card"):
            anchor = card.select_one(".card__title a[href]")
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

            date_tag = card.select_one(".card__date")
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


_MONTH_MAP = {
    "ene": 1,
    "enero": 1,
    "jan": 1,
    "january": 1,
    "feb": 2,
    "febrero": 2,
    "february": 2,
    "mar": 3,
    "marzo": 3,
    "march": 3,
    "abr": 4,
    "abril": 4,
    "apr": 4,
    "april": 4,
    "may": 5,
    "mayo": 5,
    "jun": 6,
    "junio": 6,
    "june": 6,
    "jul": 7,
    "julio": 7,
    "july": 7,
    "ago": 8,
    "agosto": 8,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "septiembre": 9,
    "setiembre": 9,
    "set": 9,
    "septe": 9,
    "september": 9,
    "oct": 10,
    "octubre": 10,
    "october": 10,
    "nov": 11,
    "noviembre": 11,
    "november": 11,
    "dic": 12,
    "diciembre": 12,
    "dec": 12,
    "december": 12,
}


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    tokens = _tokenize_date(value)
    if not tokens:
        return None

    day: int | None = None
    year: int | None = None
    month: int | None = None

    for token in tokens:
        if token.isdigit():
            number = int(token)
            if number > 31:
                year = number
            elif day is None:
                day = number
            else:
                year = number
            continue

        normalized = _normalize_month_token(token)
        if not normalized:
            continue
        month_value = _MONTH_MAP.get(normalized)
        if month_value:
            month = month_value

    if day and month and year:
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _tokenize_date(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value)
    cleaned = normalized.replace(",", " ")
    cleaned = cleaned.replace("/", " ")
    parts: list[str] = []
    for raw in cleaned.split():
        lower = raw.lower()
        if lower in {"de", "del"}:
            continue
        parts.append(raw)
    return parts


def _normalize_month_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    letters = [ch for ch in normalized if ch.isalpha()]
    return "".join(letters).lower()


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = ["ServeiJesuitaRefugiatsScraper"]
