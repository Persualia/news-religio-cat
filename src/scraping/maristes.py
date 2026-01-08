"""Scraper implementation for https://www.maristes.cat/noticies."""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Iterable, Optional

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class MaristesScraper(BaseScraper):
    site_id = "maristes"
    base_url = "https://www.maristes.cat"
    listing_url = "https://www.maristes.cat/noticies"
    default_lang = "ca"

    def __init__(self) -> None:
        super().__init__()
        self._published_cache: dict[str, Optional[datetime]] = {}

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        seen: set[str] = set()
        items: list[NewsItem] = []

        cards = listing_soup.select(".llista-notis-item")
        use_simple_iteration = False
        if not cards:
            cards = [listing_soup]
            use_simple_iteration = True

        for card in cards:
            anchors = card.find_all("a", href=True)
            anchor = None
            for candidate in anchors:
                text = candidate.get_text(strip=True)
                if text:
                    anchor = candidate
                    break
            if anchor is None:
                continue

            href = anchor.get("href", "").strip()
            if not href:
                continue

            normalized = self._normalize_url(href)
            if "/noticies/" not in normalized:
                continue
            if any(segment in normalized for segment in ("/page/", "/categoria/", "/etiqueta/", "?", "#")):
                continue
            if normalized.rstrip("/") == self.listing_url.rstrip("/"):
                continue
            if normalized in seen:
                continue
            seen.add(normalized)

            title = anchor.get_text(strip=True)
            if not title:
                continue

            metadata = {"base_url": self.base_url, "lang": self.default_lang}
            published_at = self._get_published_at(normalized)
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
            # Fallback for fixtures / alternate markup: reuse original simple anchor iteration
            for anchor in listing_soup.select("a[href]"):
                href = anchor.get("href", "").strip()
                if not href or href.startswith("#"):
                    continue
                normalized = self._normalize_url(href)
                if "/noticies/" not in normalized:
                    continue
                if any(segment in normalized for segment in ("/page/", "/categoria/", "/etiqueta/", "?", "#")):
                    continue
                if normalized.rstrip("/") == self.listing_url.rstrip("/"):
                    continue
                if normalized in seen:
                    continue
                title = anchor.get_text(strip=True)
                if not title:
                    continue
                seen.add(normalized)
                metadata = {"base_url": self.base_url, "lang": self.default_lang}
                published_at = self._get_published_at(normalized)
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


    def _get_published_at(self, url: str) -> Optional[datetime]:
        cached = self._published_cache.get(url)
        if cached is not None or url in self._published_cache:
            return cached
        try:
            soup = self._get_soup(url)
        except Exception:  # noqa: BLE001
            self._published_cache[url] = None
            return None
        published_at = _extract_published_at(soup)
        self._published_cache[url] = published_at
        return published_at


def _extract_published_at(article_soup: BeautifulSoup) -> Optional[datetime]:
    meta_keys = (
        "article:published_time",
        "datePublished",
        "pubdate",
        "publish_date",
        "article:modified_time",
        "og:updated_time",
    )
    for key in meta_keys:
        meta = article_soup.find("meta", attrs={"property": key}) or article_soup.find(
            "meta", attrs={"name": key}
        )
        if meta and meta.get("content"):
            parsed = _parse_iso(meta["content"])
            if parsed:
                return parsed

    time_tag = article_soup.find("time")
    if time_tag:
        datetime_value = time_tag.get("datetime")
        parsed = _parse_iso(datetime_value) if datetime_value else None
        if parsed:
            return parsed
        parsed = _parse_date_string(time_tag.get_text(" ", strip=True))
        if parsed:
            return parsed

    date_node = article_soup.select_one(".data")
    if date_node:
        parsed = _parse_date_string(date_node.get_text(" ", strip=True))
        if parsed:
            return parsed

    return None


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    if re.match(r".*[+-]\\d{4}$", normalized):
        normalized = normalized[:-2] + ":" + normalized[-2:]
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_date_string(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    match = re.search(r"\\b(\\d{1,2})[./-](\\d{1,2})[./-](\\d{4})\\b", value)
    if not match:
        return None
    day, month, year = match.groups()
    try:
        parsed = datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
    except ValueError:
        return None
    return parsed


__all__ = ["MaristesScraper"]
