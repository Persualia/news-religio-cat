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

        cards = listing_soup.select(".llista-notis-item")
        use_simple_iteration = False
        if not cards:
            cards = [listing_soup]
            use_simple_iteration = True

        for card in cards:
            anchors = card.find_all("a", href=True)
            anchor = None
            for candidate in anchors:
                text = candidate.get_text(strip=True)
                if text:
                    anchor = candidate
                    break
            if anchor is None:
                continue

            href = anchor.get("href", "").strip()
            if not href:
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
            # Fallback for fixtures / alternate markup: reuse original simple anchor iteration
            for anchor in listing_soup.select("a[href]"):
                href = anchor.get("href", "").strip()
                if not href or href.startswith("#"):
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


__all__ = ["MaristesScraper"]
