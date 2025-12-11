"""Scraper implementation for https://www.islamcat.org/category/actualitats/."""
from __future__ import annotations

from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper
from .feed_utils import extract_text, format_iso, parse_rfc822_datetime


class IslamatScraper(BaseScraper):
    site_id = "islamat"
    base_url = "https://islamcat.org"
    listing_url = "https://islamcat.org/category/actualitats/feed/"
    default_lang = "es"

    def _get_soup(self, url: str) -> BeautifulSoup:
        response = self._get(url)
        return BeautifulSoup(response.text, "xml")

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        for entry in listing_soup.select("item"):
            link = extract_text(entry.select_one("link"))
            if not link:
                continue
            normalized = self._normalize_url(link)
            if normalized in seen:
                continue
            seen.add(normalized)

            title = extract_text(entry.select_one("title"))
            if not title:
                continue

            summary_node = entry.find("content:encoded")
            summary = extract_text(summary_node) or extract_text(entry.select_one("description")) or normalized

            pub_node = entry.select_one("pubDate")
            published_at = parse_rfc822_datetime(pub_node.get_text(strip=True) if pub_node else None)

            metadata = {"base_url": self.base_url, "lang": self.default_lang}
            if published_at:
                metadata["published_at"] = format_iso(published_at)

            items.append(
                NewsItem(
                    source=self.site_id,
                    title=title,
                    url=normalized,
                    summary=summary,
                    published_at=published_at or utcnow(),
                    metadata=metadata,
                )
            )

        return items


__all__ = ["IslamatScraper"]
