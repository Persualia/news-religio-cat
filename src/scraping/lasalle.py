"""Scraper implementation for https://lasalle.cat/actualitat/."""
from __future__ import annotations

from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class LaSalleScraper(BaseScraper):
    site_id = "lasalle"
    base_url = "https://lasalle.cat"
    listing_url = "https://lasalle.cat/actualitat/"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        seen: set[str] = set()
        items: list[NewsItem] = []

        cards = listing_soup.select(".dslc-posts .dslc-post")
        if not cards:
            cards = listing_soup.select(".dslc-cpt-post")
        use_simple_iteration = False
        if not cards:
            cards = [listing_soup]
            use_simple_iteration = True

        for card in cards:
            anchor = card.select_one(".dslc-cpt-post-title a[href]")
            if anchor is None:
                for candidate in card.find_all("a", href=True):
                    if candidate.get_text(strip=True):
                        anchor = candidate
                        break
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


__all__ = ["LaSalleScraper"]
