"""Scraper implementation for https://jesuites.net/ca/totes-les-noticies."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class JesuitesScraper(BaseScraper):
    site_id = "jesuites"
    base_url = "https://jesuites.net"
    listing_url = "https://jesuites.net/ca/totes-les-noticies"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        seen: set[str] = set()
        items: list[NewsItem] = []
        for node in listing_soup.select(".gva-view-grid .node--type-noticia"):
            anchor = node.select_one(".post-title a[href]")
            if not anchor:
                continue
            href = anchor.get("href", "").strip()
            if not href:
                continue
            normalized = self._normalize_url(href)
            if normalized in seen:
                continue
            seen.add(normalized)

            title = anchor.get_text(strip=True)
            published_at = _extract_published_at(node)

            metadata: dict[str, str] = {"base_url": self.base_url, "lang": self.default_lang}
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


_MONTH_MAP = {
    "gen": "Jan",
    "gener": "Jan",
    "feb": "Feb",
    "febrer": "Feb",
    "mar": "Mar",
    "marc": "Mar",
    "març": "Mar",
    "abr": "Apr",
    "abril": "Apr",
    "mai": "May",
    "maig": "May",
    "jun": "Jun",
    "juny": "Jun",
    "jul": "Jul",
    "juliol": "Jul",
    "ago": "Aug",
    "ag": "Aug",
    "agost": "Aug",
    "set": "Sep",
    "setembre": "Sep",
    "oct": "Oct",
    "octubre": "Oct",
    "nov": "Nov",
    "novembre": "Nov",
    "des": "Dec",
    "desembre": "Dec",
}


def _extract_published_at(article_node: BeautifulSoup) -> datetime | None:
    date_tag = article_node.select_one(".post-created")
    if date_tag:
        parsed = _parse_date(date_tag.get_text(strip=True))
        if parsed:
            return parsed
    return None


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_date(value: str) -> datetime | None:
    cleaned = value.strip()
    if not cleaned:
        return None

    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    normalized = cleaned.lower()
    normalized = normalized.replace(" de ", " ")
    parts = [part for part in normalized.replace(",", " ").split() if part]
    if len(parts) >= 3 and parts[0].isdigit() and parts[-1].isdigit():
        day = int(parts[0])
        year = int(parts[-1])
        month_token = parts[1].strip(".")
        mapped = _MONTH_MAP.get(month_token)
        if mapped:
            try:
                dt = datetime.strptime(f"{day}-{mapped}-{year}", "%d-%b-%Y")
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
    return None


__all__ = ["JesuitesScraper"]
