"""Scraper implementation for https://www.salesians.cat/noticies/."""
from __future__ import annotations

from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class SalesiansScraper(BaseScraper):
    site_id = "salesians"
    base_url = "https://www.salesians.cat"
    listing_url = "https://www.salesians.cat/noticies/"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        seen: set[str] = set()
        items: list[NewsItem] = []

        for anchor in listing_soup.select("a[href]"):
            href = anchor.get("href", "").strip()
            if not href:
                continue
            if "salesianos.info/blog/" not in href:
                continue
            normalized = self._normalize_url(href)
            if "/blog/category/" in normalized or normalized.endswith("/category"):
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


__all__ = ["SalesiansScraper"]
