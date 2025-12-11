"""Scraper implementation for https://www.blanquerna.edu/ca/noticies."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class BlanquernaScraper(BaseScraper):
    site_id = "blanquerna"
    base_url = "https://www.blanquerna.edu"
    listing_url = "https://www.blanquerna.edu/ca/noticies"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        script = listing_soup.select_one("script#__NEXT_DATA__")
        if script is None or not script.string:
            return []

        payload = json.loads(script.string)
        items_data = _extract_items(payload)

        items: list[NewsItem] = []
        seen: set[str] = set()

        for entry in items_data:
            alias = entry.get("alias")
            if not alias:
                continue
            normalized = self._normalize_url(alias)
            if normalized in seen:
                continue
            seen.add(normalized)

            raw_title = entry.get("title")
            if isinstance(raw_title, list):
                raw_title = raw_title[0]
            title = (raw_title or "").strip()
            if not title:
                continue

            summary_html = entry.get("field_lead", [""])[0] if entry.get("field_lead") else ""
            summary = BeautifulSoup(summary_html, "lxml").get_text(" ", strip=True) if summary_html else normalized

            date_value = entry.get("field_date", [""])
            published_at = _parse_iso(date_value[0] if date_value else "")

            metadata = {"base_url": self.base_url, "lang": self.default_lang}
            if published_at:
                metadata["published_at"] = _format_iso(published_at)

            items.append(
                NewsItem(
                    source=self.site_id,
                    title=title,
                    url=normalized,
                    summary=summary,
                    published_at=published_at or utcnow(),
                    metadata=metadata,
                )
            )

        return items


def _extract_items(data: dict) -> list[dict]:
    try:
        content = data["props"]["pageProps"]["data"]["Content"]["data"]
        vista = content["field_vista"][0]["field_vista"][0]
        return vista.get("items", [])
    except (KeyError, IndexError, TypeError):
        return []


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = ["BlanquernaScraper"]
