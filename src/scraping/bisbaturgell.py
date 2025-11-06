"""Scraper implementation for https://bisbaturgell.org/ca/category/actualitat-cat."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class BisbatUrgellScraper(BaseScraper):
    site_id = "bisbaturgell"
    base_url = "https://bisbaturgell.org"
    listing_url = "https://bisbaturgell.org/ca/category/actualitat-cat"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        seen: set[str] = set()
        items: list[NewsItem] = []

        articles = listing_soup.select(".elementor-posts-container article") or listing_soup.select("article")
        use_simple_iteration = False
        if not articles:
            articles = [listing_soup]
            use_simple_iteration = True

        for article in articles:
            anchor = article.select_one(".elementor-post__title a[href]") or article.select_one("a[href]")
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

            date_node = article.select_one(".elementor-post-date")
            published_at = _parse_date(date_node.get_text(" ", strip=True)) if date_node else None

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
    "ag": "Aug",
    "ago": "Aug",
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


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None

    cleaned = value.strip().lower()
    if not cleaned:
        return None

    for token in ("d'", "d’", "del "):
        cleaned = cleaned.replace(token, " ")
    cleaned = cleaned.replace(" de ", " ")
    cleaned = cleaned.replace("  ", " ")
    parts = [part for part in cleaned.replace(",", " ").split() if part]
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

    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


__all__ = ["BisbatUrgellScraper"]
