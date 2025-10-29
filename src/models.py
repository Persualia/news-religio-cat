"""Core domain models for news scraping and delivery."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha1
from typing import Mapping, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def url_to_id(url: str) -> str:
    """Normalize a URL and return a deterministic SHA-1 identifier."""
    try:
        split = urlsplit(url)
        scheme = split.scheme or "https"
        netloc = (split.netloc or "").lower()
        if netloc.endswith(":80") and scheme == "http":
            netloc = netloc[:-3]
        if netloc.endswith(":443") and scheme == "https":
            netloc = netloc[:-4]

        path = split.path or "/"
        while "//" in path:
            path = path.replace("//", "/")
        if path != "/" and path.endswith("/"):
            path = path[:-1]

        params = []
        for key, value in parse_qsl(split.query, keep_blank_values=False):
            lowered = key.lower()
            if lowered.startswith("utm_"):
                continue
            if lowered in {"fbclid", "gclid", "yclid", "mc_cid", "mc_eid", "ref", "ref_src", "igshid"}:
                continue
            params.append((key, value))
        params.sort()
        query = urlencode(params, doseq=True)

        normalized = urlunsplit((scheme, netloc, path, query, ""))
    except Exception:  # noqa: BLE001
        normalized = url

    return sha1(normalized.encode("utf-8")).hexdigest()


@dataclass(slots=True, frozen=True)
class NewsItem:
    """Minimal representation of a news entry gathered from a source."""

    source: str
    title: str
    url: str
    retrieved_at: datetime = field(default_factory=utcnow)
    summary: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    metadata: Mapping[str, str] | None = None

    @property
    def doc_id(self) -> str:
        return url_to_id(self.url)


@dataclass(slots=True, frozen=True)
class SheetRecord:
    """Representation of a row persisted in Google Sheets."""

    date: str
    doc_id: str
    source: str
    title: str


__all__ = ["NewsItem", "SheetRecord", "url_to_id", "utcnow"]
