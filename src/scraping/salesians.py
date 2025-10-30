"""Scraper implementation for https://www.salesians.cat/noticies/."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper


class SalesiansScraper(BaseScraper):
    site_id = "salesians"
    base_url = "https://www.salesians.cat"
    listing_url = "https://www.salesians.cat/noticies/"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        seen: set[str] = set()
        items: list[NewsItem] = []

        blocks = listing_soup.select(".rss_item") or listing_soup.select("article")
        use_simple_iteration = False
        if not blocks:
            blocks = [listing_soup]
            use_simple_iteration = True

        for block in blocks:
            anchor = None
            for candidate in block.find_all("a", href=True):
                text = candidate.get_text(strip=True)
                if text:
                    anchor = candidate
                    break
                title_attr = candidate.get("title")
                if title_attr:
                    candidate.string = title_attr
                    anchor = candidate
                    break
            if anchor is None:
                continue

            href = anchor.get("href", "").strip()
            if not href or "salesianos.info/blog/" not in href:
                continue

            normalized = self._normalize_url(href)
            if "/blog/category/" in normalized or normalized.endswith("/category"):
                continue
            if normalized in seen:
                continue
            seen.add(normalized)

            title = anchor.get_text(strip=True) or anchor.get("title", "").strip()
            if not title:
                continue

            published_at = _extract_published_at(block)
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
                if not href or "salesianos.info/blog/" not in href:
                    continue
                normalized = self._normalize_url(href)
                if "/blog/category/" in normalized or normalized.endswith("/category"):
                    continue
                if normalized in seen:
                    continue
                title = anchor.get_text(strip=True) or anchor.get("title", "").strip()
                if not title:
                    continue
                seen.add(normalized)
                block = anchor.find_parent(class_="rss_item") or anchor.find_parent("article")
                published_at = _extract_published_at(block) if block else None
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


def _extract_published_at(node: BeautifulSoup | None) -> datetime | None:
    if node is None:
        return None
    date_tag = node.select_one(".rss_content small") or node.find("small")
    if not date_tag:
        return None
    parsed = _parse_date(date_tag.get_text(" ", strip=True))
    if parsed:
        return parsed
    return None


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_date(value: str) -> datetime | None:
    cleaned = value.strip()
    if not cleaned:
        return None

    lowered = cleaned.lower()
    for prefix in (
        "en ",
        "el ",
        "on ",
        "en el ",
        "en la ",
        "publicat el ",
        "publicada el ",
        "publicado el ",
    ):
        if lowered.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
            lowered = cleaned.lower()
            break

    cleaned = cleaned.strip("., ")

    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    normalized = cleaned.lower().replace(" de ", " ")
    parts = [part for part in normalized.replace(",", " ").split() if part]
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


__all__ = ["SalesiansScraper"]
