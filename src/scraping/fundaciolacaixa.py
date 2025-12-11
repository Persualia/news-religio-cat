"""Scraper implementation for https://mediahub.fundacionlacaixa.org/ca/social."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class FundacioLaCaixaScraper(BaseScraper):
    site_id = "fundaciolacaixa"
    base_url = "https://mediahub.fundacionlacaixa.org"
    listing_url = "https://mediahub.fundacionlacaixa.org/ca/social"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        data = _parse_articles(listing_soup)
        if not data:
            return []

        items: list[NewsItem] = []
        seen: set[str] = set()

        for entry in data:
            link = entry.get("mainEntityOfPage", {}).get("@id") or entry.get("url")
            if not link:
                continue

            normalized = self._normalize_url(link)
            if normalized in seen:
                continue
            seen.add(normalized)

            title = entry.get("headline") or ""
            if not title:
                continue

            summary = entry.get("description") or normalized
            published_at = _parse_iso(entry.get("datePublished"))

            metadata = {"base_url": self.base_url, "lang": self.default_lang}
            if published_at:
                metadata["published_at"] = _format_iso(published_at)

            items.append(
                NewsItem(
                    source=self.site_id,
                    title=title.strip(),
                    url=normalized,
                    summary=summary.strip(),
                    published_at=published_at or utcnow(),
                    metadata=metadata,
                )
            )

        return items


def _parse_articles(soup: BeautifulSoup) -> list[dict]:
    articles: list[dict] = []
    for node in soup.select("article.c-article"):
        link = node.select_one("a[href]")
        title = node.select_one(".c-article__title")
        date = node.select_one(".c-article__date")
        summary = node.select_one(".c-article__epigraph")

        if not link or not title:
            continue

        entry = {
            "headline": title.get_text(strip=True),
            "url": link.get("href"),
            "description": summary.get_text(" ", strip=True) if summary else "",
            "datePublished": _parse_local_date(date.get_text(strip=True) if date else None),
        }
        articles.append(entry)
    return articles


def _parse_local_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        day, month, year = value.split(".")
        dt = datetime(int("20" + year) if len(year) == 2 else int(year), int(month), int(day), tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None
    return dt.isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = ["FundacioLaCaixaScraper"]
