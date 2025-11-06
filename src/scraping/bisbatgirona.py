"""Scraper implementation for https://www.bisbatgirona.cat/ca/noticies.html."""
from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from models import NewsItem, utcnow

from .base import BaseScraper


class BisbatGironaScraper(BaseScraper):
    site_id = "bisbatgirona"
    base_url = "https://www.bisbatgirona.cat"
    listing_url = "https://www.bisbatgirona.cat/ca/noticies.html"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        seen: set[str] = set()
        items: list[NewsItem] = []

        articles = listing_soup.select(".llistatNoticies .noticia") or listing_soup.select(".noticia")
        use_simple_iteration = False
        if not articles:
            articles = [listing_soup]
            use_simple_iteration = True

        for article in articles:
            anchor = article.select_one(".titolNoticia a[href]") or article.select_one("a[href]")
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

            published_at = _parse_date(article)

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


def _parse_date(article: Tag) -> datetime | None:
    data_box = article.select_one(".data")
    if data_box is None:
        return None

    day_node = data_box.select_one(".mes")
    month_node = data_box.select_one(".mes-text")
    year_node = data_box.select_one(".any")
    if day_node is None or month_node is None or year_node is None:
        return None

    day_text = day_node.get_text(strip=True)
    try:
        day = int(day_text)
    except ValueError:
        return None

    month_raw = month_node.get_text(" ", strip=True)
    month_normalized = _normalize_month(month_raw)
    month = _MONTH_MAP.get(month_normalized)
    if month is None:
        return None

    year_text = year_node.get_text(" ", strip=True)
    year_match = re.search(r"\d{4}", year_text)
    if year_match is None:
        return None

    year = int(year_match.group(0))

    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


def _normalize_month(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.replace("\u00a0", " ")
    normalized = normalized.replace("d'", "")
    normalized = normalized.replace("de ", "")
    normalized = normalized.replace("del ", "")
    normalized = normalized.replace(".", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.strip()
    normalized = normalized.lower()
    normalized = normalized.replace("ç", "c")
    return normalized


__all__ = ["BisbatGironaScraper"]
