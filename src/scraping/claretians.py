"""Scraper implementation for https://claretpaulus.org/ca/."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class ClaretiansScraper(BaseScraper):
    site_id = "claretians"
    base_url = "https://claretpaulus.org"
    listing_url = "https://claretpaulus.org/ca/actualitat/"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        seen: set[str] = set()
        items: list[NewsItem] = []

        articles = listing_soup.select(".articles-list article")
        if not articles:
            articles = listing_soup.select(".blog-shortcode article")
        use_simple_iteration = False
        if not articles:
            articles = [listing_soup]
            use_simple_iteration = True

        for article in articles:
            anchor = article.select_one(".entry-title a[href]")
            if anchor is None:
                for candidate in article.find_all("a", href=True):
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

            date_value = article.get("data-date") or article.find_parent(attrs={"data-date": True})
            date_str: str | None = None
            if isinstance(date_value, str):
                date_str = date_value
            elif date_value is not None:
                date_str = date_value.get("data-date")
            published_at = _parse_iso(date_str) if date_str else None

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


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


__all__ = ["ClaretiansScraper"]
