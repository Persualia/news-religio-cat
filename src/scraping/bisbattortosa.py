"""Scraper implementation for https://www.bisbattortosa.org/actualitat/."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper, ScraperUnexpectedContentError


class BisbatTortosaScraper(BaseScraper):
    site_id = "bisbattortosa"
    base_url = "https://www.bisbattortosa.org"
    listing_url = (
        "https://www.bisbattortosa.org/wp-json/wp/v2/posts"
        "?per_page=9&_fields=link,title.rendered,date"
    )
    default_lang = "ca"

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


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _preview(value: str, max_length: int = 160) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= max_length:
        return collapsed
    return f"{collapsed[:max_length]}..."


__all__ = ["BisbatTortosaScraper"]
