"""Scraper implementation for https://www.caritasgirona.cat/ca/1715/noticies.html."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper

_MONTHS = {
    "gener": 1,
    "febrer": 2,
    "març": 3,
    "marc": 3,
    "abril": 4,
    "maig": 5,
    "juny": 6,
    "juliol": 7,
    "agost": 8,
    "setembre": 9,
    "setembre": 9,
    "octubre": 10,
    "novembre": 11,
    "desembre": 12,
}


class CaritasGironaScraper(BaseScraper):
    site_id = "caritasgirona"
    base_url = "https://www.caritasgirona.cat"
    listing_url = "https://www.caritasgirona.cat/ca/1715/noticies.html"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        for block in listing_soup.select(".bloc_noticia"):
            link = _extract_link(block)
            if not link:
                continue
            normalized = self._normalize_url(link)
            if normalized in seen:
                continue
            seen.add(normalized)

            title = block.select_one("h3")
            if title is None:
                continue
            title_text = title.get_text(strip=True)
            if not title_text:
                continue

            summary = _extract_summary(block) or normalized
            published_at = _parse_date(block.select_one(".data_noticia"))

            metadata = {"base_url": self.base_url, "lang": self.default_lang}
            if published_at:
                metadata["published_at"] = _format_iso(published_at)

            items.append(
                NewsItem(
                    source=self.site_id,
                    title=title_text,
                    url=normalized,
                    summary=summary,
                    published_at=published_at or utcnow(),
                    metadata=metadata,
                )
            )

        return items


def _extract_link(block: BeautifulSoup) -> str:
    share = block.select_one(".twitter-share-button")
    if share is None:
        return ""
    return share.get("data-url", "").strip()


def _extract_summary(block: BeautifulSoup) -> str:
    summary_box = block.select_one(".col_esquerra_curt div div")
    if summary_box is None:
        summary_box = block.select_one(".col_esquerra_curt")
    if summary_box is None:
        return ""
    return summary_box.get_text(" ", strip=True)


def _parse_date(node: BeautifulSoup | None) -> datetime | None:
    if node is None:
        return None
    parts = [part.strip() for part in node.stripped_strings if part.strip()]
    if len(parts) < 3:
        return None
    day, month_name, year = parts[0], parts[1], parts[2]
    if not day.isdigit() or not year.isdigit():
        return None
    month = _MONTHS.get(month_name.lower())
    if not month:
        return None
    try:
        return datetime(int(year), month, int(day), tzinfo=timezone.utc)
    except ValueError:
        return None


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = ["CaritasGironaScraper"]
