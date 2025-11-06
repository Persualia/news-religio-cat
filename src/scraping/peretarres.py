"""Scraper implementation for https://www.peretarres.org/actualitat/noticies."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import unicodedata
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from models import NewsItem, utcnow

from .base import BaseScraper


class PeretarresScraper(BaseScraper):
    site_id = "peretarres"
    base_url = "https://www.peretarres.org"
    listing_url = "https://www.peretarres.org/actualitat/noticies"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        for entry in _iter_entries(listing_soup):
            href = entry.link.get("href", "").strip()
            if not href:
                continue
            normalized = self._normalize_url(href)
            if normalized in seen:
                continue
            seen.add(normalized)

            title = entry.link.get_text(strip=True)
            if not title:
                continue

            published_at = _parse_date(entry.date_text)

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

        return items


@dataclass(frozen=True)
class _Entry:
    link: Tag
    date_text: str


def _iter_entries(soup: BeautifulSoup) -> Iterable[_Entry]:
    featured_link = soup.select_one(".titol-noticia-destacada")
    link: Tag | None = None
    if featured_link is not None:
        if featured_link.name == "a":
            link = featured_link
        else:
            link = featured_link.select_one("a")
    if link is not None:
        date_tag = soup.select_one(".btn.btn-default.font-20.mt-30")
        date_text = date_tag.get_text(strip=True) if date_tag else ""
        yield _Entry(link=link, date_text=date_text)

    for card in soup.select(".image-box.style-2"):
        link_tag = card.select_one("a.titol-noticia-coneixement") or card.select_one("h3 a") or card.select_one("a")
        if link_tag is None:
            continue
        date_tag = card.select_one(".taronja-negreta")
        date_text = date_tag.get_text(strip=True) if date_tag else ""
        yield _Entry(link=link_tag, date_text=date_text)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = unicodedata.normalize("NFKD", value)
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    for fmt in ("%d.%m.%y", "%d.%m.%Y", "%d/%m/%Y", "%d/%m/%y"):
        try:
            parsed = datetime.strptime(cleaned, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = ["PeretarresScraper"]
