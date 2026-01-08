"""Scraper implementation for https://www.poblet.cat/ca/actualitat/noticies/."""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import re
from typing import Iterable, Optional

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class MoenstirDelPobletScraper(BaseScraper):
    site_id = "moenstirdelpoblet"
    base_url = "https://www.poblet.cat"
    listing_url = "https://www.poblet.cat/ca/actualitat/noticies/"
    default_lang = "ca"

    def __init__(self) -> None:
        super().__init__()
        self._lastmod_cache: dict[str, datetime] | None = None

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        for box in listing_soup.select(".news-box h2 a"):
            href = box.get("href", "").strip()
            if not href:
                continue
            normalized = self._normalize_url(href)
            if normalized in seen:
                continue
            seen.add(normalized)

            title = box.get_text(strip=True)
            if not title:
                continue

            published_at = self._get_lastmod(normalized)
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


    def _get_lastmod(self, url: str) -> Optional[datetime]:
        mapping = self._ensure_lastmod_cache()
        if not mapping:
            return None
        return mapping.get(url)


    def _ensure_lastmod_cache(self) -> dict[str, datetime]:
        if self._lastmod_cache is not None:
            return self._lastmod_cache

        sitemap_index_url = "https://www.poblet.cat/sitemap.xml"
        sitemap_url = sitemap_index_url
        try:
            index_response = self._get(sitemap_index_url)
            index_soup = BeautifulSoup(index_response.text, "xml")
            for loc in index_soup.select("sitemap > loc"):
                if "sitemap_lang_ca" in loc.get_text():
                    sitemap_url = loc.get_text(strip=True)
                    break
        except Exception:  # noqa: BLE001
            sitemap_url = sitemap_index_url

        try:
            sitemap_response = self._get(sitemap_url)
            content = sitemap_response.content
            if content[:2] == b"\\x1f\\x8b":
                content = gzip.decompress(content)
            sitemap_text = content.decode("utf-8", errors="replace")
            sitemap_soup = BeautifulSoup(sitemap_text, "xml")
        except Exception:  # noqa: BLE001
            self._lastmod_cache = {}
            return self._lastmod_cache

        mapping: dict[str, datetime] = {}
        for url_node in sitemap_soup.select("url"):
            loc = url_node.find("loc")
            lastmod = url_node.find("lastmod")
            if loc is None or lastmod is None:
                continue
            loc_text = loc.get_text(strip=True)
            lastmod_text = lastmod.get_text(strip=True)
            parsed = _parse_iso(lastmod_text)
            if not loc_text or not parsed:
                continue
            normalized = self._normalize_url(loc_text)
            mapping[normalized] = parsed

        self._lastmod_cache = mapping
        return mapping


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


__all__ = ["MoenstirDelPobletScraper"]
