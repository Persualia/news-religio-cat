"""Scraper implementation for http://www.carmelcat.cat/."""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from models import NewsItem, utcnow

from .base import BaseScraper


class CarmelitesDescalcosScraper(BaseScraper):
    site_id = "carmelitesdescalcosdecatalunya"
    base_url = "http://www.carmelcat.cat"
    listing_url = "http://www.carmelcat.cat/"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        container = listing_soup.select_one("td[valign='top']")
        if container is None:
            return []

        items: list[NewsItem] = []
        seen: set[str] = set()

        normalized_listing = self._normalize_url(self.listing_url)

        for heading in container.find_all("h2"):
            title = heading.get_text(strip=True)
            if not title:
                continue

            link = _find_link(heading)
            if not link:
                slug = _slugify(title)
                normalized = _build_slug_url(normalized_listing, slug)
            else:
                normalized = self._normalize_url(link)

            if normalized in seen:
                continue
            seen.add(normalized)

            summary = _extract_summary(heading) or title

            items.append(
                NewsItem(
                    source=self.site_id,
                    title=title,
                    url=normalized,
                    summary=summary,
                    published_at=utcnow(),
                    metadata={"base_url": self.base_url, "lang": self.default_lang},
                )
            )

        return items


def _find_link(heading: Tag) -> str:
    column = heading.find_parent("td")

    for anchor in heading.find_all("a", href=True):
        href = anchor["href"].strip()
        if href and _is_valid_article_link(anchor):
            return href

    node: Tag | None = heading
    while node is not None:
        node = node.find_next()
        if node is None:
            break
        parent_td = node.find_parent("td") if hasattr(node, "find_parent") else None
        if column is not None and parent_td is not column and node is not column:
            break
        if isinstance(node, Tag):
            if node.name == "h2":
                break
            if node.name == "a" and node.get("href"):
                href = node["href"].strip()
                if href and _is_valid_article_link(node):
                    return href
    return ""


def _extract_summary(heading: Tag) -> str:
    fragments: list[str] = []
    node: Tag | None = heading
    while node is not None:
        node = node.find_next_sibling()
        if node is None or node.name == "h2":
            break
        if node.name == "p":
            text = node.get_text(" ", strip=True)
            if text:
                fragments.append(text)
    return " ".join(fragments)


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = re.sub(r"[^\w\s-]", "", normalized)
    normalized = re.sub(r"[\s_-]+", "-", normalized).strip("-")
    return normalized or "noticia"


def _build_slug_url(listing_url: str, slug: str) -> str:
    if listing_url.endswith("/"):
        return f"{listing_url}#{slug}"
    return f"{listing_url}/#{slug}"


def _is_valid_article_link(anchor: Tag) -> bool:
    href = anchor.get("href", "").strip().lower()
    if not href or href.startswith(("mailto:", "javascript:")):
        return False
    path = href.split("#", 1)[0].split("?", 1)[0]
    if path.endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".tiff", ".ico", ".pdf")):
        return False
    return True


__all__ = ["CarmelitesDescalcosScraper"]
