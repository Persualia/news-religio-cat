"""Scraper implementation for https://escolapia.cat/actualitat/."""
from __future__ import annotations

import html
import logging
from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


logger = logging.getLogger(__name__)


class EscolaPiaScraper(BaseScraper):
    site_id = "escolapia"
    base_url = "https://escolapia.cat"
    listing_url = "https://escolapia.cat/actualitat/"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        seen: set[str] = set()
        items: list[NewsItem] = []

        cards = listing_soup.select(".fusion-post-cards .post-card")
        if not cards:
            cards = listing_soup.select(".post-card")
        use_simple_iteration = False
        if not cards:
            cards = [listing_soup]
            use_simple_iteration = True

        for card in cards:
            anchor = card.select_one(".fusion-title a[href]")
            if anchor is None:
                for candidate in card.find_all("a", href=True):
                    if candidate.get_text(strip=True):
                        anchor = candidate
                        break
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

            date_tag = card.select_one(".fusion-tb-published-date")
            published_at = _parse_date(date_tag.get_text(strip=True)) if date_tag else None

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

    def scrape(self, *, limit: int | None = None) -> list[NewsItem]:
        try:
            items = self._scrape_via_api()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Scraper '%s' failed to load WordPress API feed; falling back to HTML listing: %s",
                self.site_id,
                exc,
            )
            return super().scrape(limit=limit)

        if not items:
            return super().scrape(limit=limit)

        effective_limit = 9
        if limit is not None:
            effective_limit = min(limit, effective_limit)
        return items[:effective_limit]

    def _scrape_via_api(self) -> list[NewsItem]:
        response = self._get(
            "https://escolapia.cat/wp-json/wp/v2/posts?per_page=20&_fields=link,title,date"
        )
        payload = response.json()
        if not isinstance(payload, list):
            return []
        return self._extract_items_from_api_payload(payload)

    def _extract_items_from_api_payload(self, payload: list[dict]) -> list[NewsItem]:
        seen: set[str] = set()
        items: list[NewsItem] = []

        for row in payload:
            if not isinstance(row, dict):
                continue

            href = str(row.get("link") or "").strip()
            if not href:
                continue

            normalized = self._normalize_url(href)
            if normalized in seen or "/actualitat/" not in normalized:
                continue
            seen.add(normalized)

            title_data = row.get("title") or {}
            rendered_title = title_data.get("rendered") if isinstance(title_data, dict) else ""
            title = html.unescape(str(rendered_title or "")).strip()
            if not title:
                continue

            published_at = _parse_api_date(str(row.get("date") or ""))
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


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_date(value: str) -> datetime | None:
    cleaned = value.strip()
    if not cleaned:
        return None

    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    lowered = cleaned.lower().replace(" de ", " ")
    parts = [part for part in lowered.replace(",", " ").split() if part]
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


def _parse_api_date(value: str) -> datetime | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


__all__ = ["EscolaPiaScraper"]
