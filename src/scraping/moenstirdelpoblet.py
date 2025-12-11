"""Scraper implementation for https://www.poblet.cat/ca/actualitat/noticies/."""
from __future__ import annotations

from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class MoenstirDelPobletScraper(BaseScraper):
    site_id = "moenstirdelpoblet"
    base_url = "https://www.poblet.cat"
    listing_url = "https://www.poblet.cat/ca/actualitat/noticies/"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        for box in listing_soup.select(".news-box h2 a"):
            href = box.get("href", "").strip()
            if not href:
                continue
            normalized = self._normalize_url(href)
            if normalized in seen:
                continue
            seen.add(normalized)

            title = box.get_text(strip=True)
            if not title:
                continue

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


__all__ = ["MoenstirDelPobletScraper"]
