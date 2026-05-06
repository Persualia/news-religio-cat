"""Scraper implementation for https://salesianos.info/ca/feed/."""
from __future__ import annotations

from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper
from .feed_utils import extract_text, format_iso, parse_rfc822_datetime


class SalesiansScraper(BaseScraper):
    site_id = "salesians"
    base_url = "https://salesianos.info"
    listing_url = "https://salesianos.info/ca/feed/"
    default_lang = "ca"

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

            date_node = entry.select_one("pubDate") or entry.select_one("pubdate")
            published_at = parse_rfc822_datetime(extract_text(date_node))

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


__all__ = ["SalesiansScraper"]
