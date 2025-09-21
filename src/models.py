"""Dataclasses representing scraped articles and derived chunks."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha1
from typing import Optional


ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(ISO_FORMAT)


def url_to_id(url: str) -> str:
    """Generate the deterministic OpenSearch document ID from the URL."""
    return sha1(url.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class Article:
    site: str
    url: str
    lang: str
    title: str
    content: str
    indexed_at: datetime = field(default_factory=utcnow)
    author: Optional[str] = None
    description: Optional[str] = None
    published_at: Optional[datetime] = None

    def to_document(self) -> dict:
        """Convert the article into an OpenSearch document payload."""
        doc = {
            "site": self.site,
            "url": self.url,
            "lang": self.lang,
            "title": self.title,
            "content": self.content,
            "indexed_at": _to_iso(self.indexed_at),
        }
        if self.author:
            doc["author"] = self.author
        if self.description:
            doc["description"] = self.description
        if self.published_at:
            doc["published_at"] = _to_iso(self.published_at)
        return doc

    @property
    def doc_id(self) -> str:
        return url_to_id(self.url)


@dataclass(slots=True)
class Chunk:
    article: Article
    chunk_ix: int
    content: str
    content_vec: list[float]

    def to_document(self) -> dict:
        doc = {
            "site": self.article.site,
            "url": self.article.url,
            "lang": self.article.lang,
            "author": self.article.author,
            "published_at": _to_iso(self.article.published_at)
            if self.article.published_at
            else None,
            "indexed_at": _to_iso(self.article.indexed_at),
            "chunk_ix": self.chunk_ix,
            "content": self.content,
            "content_vec": self.content_vec,
        }
        return {k: v for k, v in doc.items() if v is not None}

    @property
    def doc_id(self) -> str:
        return f"{self.article.doc_id}:{self.chunk_ix:03d}"


__all__ = ["Article", "Chunk", "url_to_id"]
