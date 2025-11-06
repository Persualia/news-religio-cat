"""Scraper implementation for https://www.bisbatlleida.org/ca/news."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class BisbatLleidaScraper(BaseScraper):
    site_id = "bisbatlleida"
    base_url = "https://www.bisbatlleida.org"
    listing_url = "https://www.bisbatlleida.org/ca/news"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        seen: set[str] = set()
        items: list[NewsItem] = []

        rows = listing_soup.select(".view-content .noticia") or listing_soup.select(".views-row")
        use_simple_iteration = False
        if not rows:
            rows = [listing_soup]
            use_simple_iteration = True

        for row in rows:
            anchor = row.select_one(".views-field-title a[href]") or row.select_one("a[href]")
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

            date_node = row.select_one(".views-field-created")
            date_text = ""
            if date_node:
                date_text = date_node.get_text(" ", strip=True)
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


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None

    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


__all__ = ["BisbatLleidaScraper"]
