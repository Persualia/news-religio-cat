"""Scraper implementation for https://bisbatsolsona.cat/comunicacio/noticies/."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class BisbatSolsonaScraper(BaseScraper):
    site_id = "bisbatsolsona"
    base_url = "https://bisbatsolsona.cat"
    listing_url = "https://bisbatsolsona.cat/comunicacio/noticies/"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        seen: set[str] = set()
        items: list[NewsItem] = []

        articles = listing_soup.select(".actualitat-container article") or listing_soup.select("article.post")
        use_simple_iteration = False
        if not articles:
            articles = [listing_soup]
            use_simple_iteration = True

        for article in articles:
            anchor = article.select_one("a[href]")
            if anchor is None:
                continue

            href = anchor.get("href", "").strip()
            if not href:
                continue

            normalized = self._normalize_url(href)
            if normalized in seen:
                continue
            seen.add(normalized)

            title_tag = article.select_one("h2") or anchor.select_one("h2")
            title = title_tag.get_text(strip=True) if title_tag else anchor.get_text(strip=True)
            if not title:
                continue

            time_tag = article.select_one("time[datetime]")
            published_at = _parse_iso(time_tag.get("datetime", "")) if time_tag else None

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


__all__ = ["BisbatSolsonaScraper"]
