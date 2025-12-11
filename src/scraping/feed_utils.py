"""Utility helpers for RSS-based scrapers."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape

from bs4 import BeautifulSoup, Tag


def extract_text(node: Tag | BeautifulSoup | None) -> str:
    """Return sanitized text content for RSS elements."""

    if node is None:
        return ""

    raw = node.get_text()
    if not raw:
        return ""

    raw = raw.strip()
    if "<" in raw:
        return BeautifulSoup(raw, "lxml").get_text(" ", strip=True)

    normalized = " ".join(unescape(raw).split())
    return normalized


def parse_rfc822_datetime(value: str | None) -> datetime | None:
    """Parse RFC 822/1123 date strings into timezone-aware UTC datetimes."""

    if not value:
        return None

    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_iso(value: datetime) -> str:
    """Return ISO-formatted UTC timestamps for metadata."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = ["extract_text", "format_iso", "parse_rfc822_datetime"]
