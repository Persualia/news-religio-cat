"""Scraper implementation for https://esglesia.barcelona/noticies/."""
from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from models import NewsItem, utcnow

from .base import BaseScraper


class BisbatBarcelonaScraper(BaseScraper):
    site_id = "bisbatbarcelona"
    base_url = "https://esglesia.barcelona"
    listing_url = "https://esglesia.barcelona/noticies/"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        seen: set[str] = set()
        items: list[NewsItem] = []

        articles = listing_soup.select(".ultimes-noticies article") or listing_soup.select("article")
        use_simple_iteration = False
        if not articles:
            articles = [listing_soup]
            use_simple_iteration = True

        for article in articles:
            anchor = article.select_one(".noticia-header a[href]") or article.select_one("a[href]")
            if anchor is None:
                continue

            href = anchor.get("href", "").strip()
            if not href:
                continue

            normalized = self._normalize_url(href)
            if normalized in seen:
                continue
            seen.add(normalized)

            title_tag = anchor.select_one("h2") or article.select_one("h2")
            title = title_tag.get_text(strip=True) if title_tag else anchor.get_text(strip=True)
            if not title:
                continue

            date_tag = article.select_one(".date")
            published_at = _parse_date(date_tag) if date_tag else None

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


def _parse_date(container: Tag) -> datetime | None:
    if container is None:
        return None

    text = container.get_text(" ", strip=True)
    if not text:
        return None

    normalized = unicodedata.normalize("NFKD", text)
    normalized = normalized.replace("\u00a0", " ")
    normalized = normalized.replace(",", " ")
    normalized = normalized.replace(".", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.strip().lower()
    if not normalized:
        return None

    match = re.search(r"(\d{1,2})\s+([a-zà-ú]+)\s+(\d{4})", normalized)
    if match is None:
        return None

    day = int(match.group(1))
    month_key = match.group(2)
    month_key = month_key.replace("ç", "c")
    month = _MONTH_MAP.get(month_key)
    if month is None:
        return None

    year = int(match.group(3))

    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


__all__ = ["BisbatBarcelonaScraper"]
