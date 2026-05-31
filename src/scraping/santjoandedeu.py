"""Scraper implementation for https://sjd.es/noticias/."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Iterable, Optional

import httpx
from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper, MAX_ITEMS_PER_SOURCE, ScraperNoArticlesError, ScraperUnexpectedContentError


class SantJoanDeDeuScraper(BaseScraper):
    site_id = "santjoandedeu"
    base_url = "https://sjd.es"
    listing_url = (
        "https://sjd.es/wp-json/wp/v2/posts"
        "?per_page=9&_fields=link,title.rendered,date"
    )
    fallback_url = "https://sjd.es/noticias/"
    ajax_url = "https://sjd.es/wp-admin/admin-ajax.php"
    default_lang = "es"

    def scrape(self, *, limit: Optional[int] = None) -> list[NewsItem]:
        try:
            return super().scrape(limit=limit)
        except (httpx.HTTPStatusError, ScraperNoArticlesError, ScraperUnexpectedContentError):
            items = self._scrape_fallback_listing()
            if not items:
                raise ScraperNoArticlesError(self.site_id)
            effective_limit = MAX_ITEMS_PER_SOURCE
            if limit is not None:
                effective_limit = min(limit, MAX_ITEMS_PER_SOURCE)
            return items[:effective_limit]

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        text = listing_soup.get_text(strip=True)
        if not text:
            raise ScraperUnexpectedContentError(
                self.site_id,
                "La API de WordPress devolvió una respuesta vacía.",
            )

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ScraperUnexpectedContentError(
                self.site_id,
                f"La API de WordPress no devolvió JSON válido. Vista previa: {_preview(text)}",
            ) from exc
        if not isinstance(payload, list):
            raise ScraperUnexpectedContentError(
                self.site_id,
                f"La API de WordPress devolvió {type(payload).__name__}; se esperaba una lista.",
            )

        items: list[NewsItem] = []
        seen: set[str] = set()

        for entry in payload:
            link = (entry.get("link") or "").strip()
            if not link:
                continue
            normalized = self._normalize_url(link)
            if normalized in seen:
                continue
            seen.add(normalized)

            title_html = (entry.get("title", {}) or {}).get("rendered", "")
            title = _clean_text(title_html)
            if not title:
                continue

            published_at = _parse_datetime(entry.get("date"))

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

    def _scrape_fallback_listing(self) -> list[NewsItem]:
        params = {
            "action": "alm_get_posts",
            "query_type": "standard",
            "id": "7350557918",
            "post_id": "0",
            "slug": "home",
            "canonical_url": self.fallback_url,
            "posts_per_page": "9",
            "page": "0",
            "offset": "0",
            "original_offset": "0",
            "post_type": "post",
            "repeater": "default",
            "seo_start_page": "0",
            "category__not_in": "365",
            "order": "DESC",
            "orderby": "date",
            "lang": self.default_lang,
            "currentPage": "1",
        }
        response = self._client.get(
            self.ajax_url,
            params=params,
            headers={"Referer": self.fallback_url},
        )
        response.raise_for_status()

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ScraperUnexpectedContentError(
                self.site_id,
                f"El fallback HTML/AJAX no devolvió JSON válido. Vista previa: {_preview(response.text)}",
            ) from exc

        html = payload.get("html") if isinstance(payload, dict) else None
        if not html:
            raise ScraperUnexpectedContentError(
                self.site_id,
                "El fallback HTML/AJAX no devolvió el campo 'html' esperado.",
            )

        soup = BeautifulSoup(html, "lxml")
        return list(self._extract_items_from_fallback_html(soup))

    def _extract_items_from_fallback_html(self, soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        for article in soup.select("article.entry"):
            link_node = article.select_one("a.link[href]")
            title_node = article.select_one(".entry-title")
            if not link_node or not title_node:
                continue

            link = (link_node.get("href") or "").strip()
            title = title_node.get_text(" ", strip=True)
            if not link or not title:
                continue

            normalized = self._normalize_url(link)
            if normalized in seen:
                continue
            seen.add(normalized)

            published_at = _parse_spanish_date(_extract_fallback_date_text(article))
            metadata = {
                "base_url": self.base_url,
                "lang": self.default_lang,
                "fallback": self.fallback_url,
            }
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


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return BeautifulSoup(value, "html.parser").get_text(strip=True)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_fallback_date_text(article: BeautifulSoup) -> str | None:
    for span in article.select("span"):
        text = span.get_text(" ", strip=True)
        if text:
            return text
    return None


def _parse_spanish_date(value: str | None) -> datetime | None:
    if not value:
        return None
    parts = value.strip().lower().split()
    if len(parts) != 3:
        return None

    month = _SPANISH_MONTHS.get(parts[1])
    if not month:
        return None
    try:
        return datetime(int(parts[2]), month, int(parts[0]), tzinfo=timezone.utc)
    except ValueError:
        return None


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _preview(value: str, max_length: int = 160) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= max_length:
        return collapsed
    return f"{collapsed[:max_length]}..."


_SPANISH_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


__all__ = ["SantJoanDeDeuScraper"]
