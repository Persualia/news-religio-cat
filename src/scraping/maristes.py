"""Scraper implementation for https://www.maristes.cat/noticies."""
from __future__ import annotations

from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class MaristesScraper(BaseScraper):
    site_id = "maristes"
    base_url = "https://www.maristes.cat"
    listing_url = "https://www.maristes.cat/noticies"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        seen: set[str] = set()
        items: list[NewsItem] = []

        for anchor in listing_soup.select("a[href]"):
            href = anchor.get("href", "").strip()
            if not href:
                continue
            if href.startswith("#"):
                continue

            normalized = self._normalize_url(href)
            if "/noticies/" not in normalized:
                continue
            if any(segment in normalized for segment in ("/page/", "/categoria/", "/etiqueta/", "?", "#")):
                continue
            if normalized.rstrip("/") == self.listing_url.rstrip("/"):
                continue
            if normalized in seen:
                continue
            seen.add(normalized)

            title = anchor.get_text(strip=True)
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


__all__ = ["MaristesScraper"]
