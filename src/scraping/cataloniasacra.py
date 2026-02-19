"""Scraper implementation for https://www.cataloniasacra.cat/category/noticies/."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class CataloniaSacraScraper(BaseScraper):
    site_id = "cataloniasacra"
    base_url = "https://www.cataloniasacra.cat"
    listing_url = "https://www.cataloniasacra.cat/category/noticies/"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        blocks = listing_soup.select("article.et_pb_post")

        for block in blocks:
            anchor = block.select_one("h2.entry-title a")
            date_node = block.select_one("p.post-meta .published")
            summary_node = block.select_one("div.post-content-inner p")

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

            summary = summary_node.get_text(" ", strip=True) if summary_node else normalized
            published_at = _parse_date(date_node.get_text(strip=True) if date_node else None)

            metadata = {"base_url": self.base_url, "lang": self.default_lang}
            if published_at:
                metadata["published_at"] = _format_iso(published_at)

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


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        day, month, year = value.split("/")
        return datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = ["CataloniaSacraScraper"]
