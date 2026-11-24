"""Scraper implementation for https://www.caritasgirona.cat/noticies/.

The site moved to WordPress in November 2026. The listing cards only carry the
title and link, so the publication date and summary come from each article page
(JSON-LD ``datePublished`` and the first paragraphs of the body). The WordPress
REST API answers 403 and the news RSS feed is empty, so HTML is the only source.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import MAX_ITEMS_PER_SOURCE, BaseScraper

logger = logging.getLogger(__name__)

_SUMMARY_MAX_CHARS = 500


class CaritasGironaScraper(BaseScraper):
    site_id = "caritasgirona"
    base_url = "https://www.caritasgirona.cat"
    listing_url = "https://www.caritasgirona.cat/noticies/"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        for card in listing_soup.select(".multiple-posts-item-container"):
            anchor = card.select_one("a[href]")
            if anchor is None:
                continue
            normalized = self._normalize_url(anchor["href"].strip())
            if "/noticias/" not in normalized or normalized in seen:
                continue
            seen.add(normalized)

            title_node = card.select_one(".title")
            title = title_node.get_text(" ", strip=True) if title_node else ""
            if not title:
                continue

            description = card.select_one(".description")
            summary = description.get_text(" ", strip=True) if description else ""
            published_at = None
            if len(items) < MAX_ITEMS_PER_SOURCE:
                detail_date, detail_summary = self._fetch_details(normalized)
                published_at = detail_date
                summary = summary or detail_summary

            metadata = {"base_url": self.base_url, "lang": self.default_lang}
            if published_at:
                metadata["published_at"] = _format_iso(published_at)

            items.append(
                NewsItem(
                    source=self.site_id,
                    title=title,
                    url=normalized,
                    summary=summary or normalized,
                    published_at=published_at or utcnow(),
                    metadata=metadata,
                )
            )

        return items

    def _fetch_details(self, url: str) -> tuple[datetime | None, str]:
        try:
            soup = self._get_soup(url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch Càritas Girona article %s: %s", url, exc)
            return None, ""
        return extract_published_at(soup), extract_summary(soup)


def extract_published_at(article_soup: BeautifulSoup) -> datetime | None:
    for script in article_soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        nodes = data.get("@graph", [data]) if isinstance(data, dict) else data
        for node in nodes if isinstance(nodes, list) else []:
            if isinstance(node, dict) and node.get("datePublished"):
                parsed = _parse_iso(node["datePublished"])
                if parsed:
                    return parsed

    date_node = article_soup.select_one(".single-header-container-content .date")
    if date_node is not None:
        try:
            return datetime.strptime(date_node.get_text(strip=True), "%d/%m/%Y").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def extract_summary(article_soup: BeautifulSoup) -> str:
    parts: list[str] = []
    length = 0
    for paragraph in article_soup.select(".wysiwyg-content p"):
        text = paragraph.get_text(" ", strip=True)
        if not text:
            continue
        parts.append(text)
        length += len(text)
        if length >= _SUMMARY_MAX_CHARS:
            break
    return " ".join(parts)


def _parse_iso(value: str) -> datetime | None:
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


__all__ = ["CaritasGironaScraper"]
