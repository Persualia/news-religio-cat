"""Helpers to build chat-ready context windows from Qdrant search results."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Mapping, Sequence

from .qdrant_search import SearchResult, search_articles, search_chunks

try:  # pragma: no cover - optional dependency during tests
    from qdrant_client import QdrantClient
except ModuleNotFoundError:  # pragma: no cover
    QdrantClient = Any  # type: ignore[misc]


DEFAULT_CHUNK_LIMIT = 18
DEFAULT_PER_ARTICLE = 3
DEFAULT_ARTICLE_LIMIT = 8
DEFAULT_CHUNK_CANDIDATE_MULTIPLIER = 6
DEFAULT_MAX_TOKENS = 1800
DEFAULT_MIN_ARTICLES = 3
DEFAULT_MIN_SITES = 2


@dataclass(slots=True)
class ChunkContext:
    """Represents a single chunk of content selected for the response window."""

    chunk_id: str
    article_id: str
    content: str
    chunk_ix: int | None
    site: str | None
    url: str | None
    published_at: str | None
    published_at_ts: int | None
    indexed_at: str | None
    indexed_at_ts: int | None
    score: float
    vector_score: float
    recency_weight: float
    token_count: int


@dataclass(slots=True)
class ArticleContext:
    """Container for metadata and chunks belonging to the same article."""

    article_id: str
    site: str | None = None
    url: str | None = None
    title: str | None = None
    description: str | None = None
    author: str | None = None
    published_at: str | None = None
    published_at_ts: int | None = None
    indexed_at: str | None = None
    indexed_at_ts: int | None = None
    best_score: float = 0.0
    best_recency: float = 0.0
    chunks: list[ChunkContext] = field(default_factory=list)

    def trimmed(
        self,
        chunks: Sequence[ChunkContext],
        *,
        best_score: float | None = None,
        best_recency: float | None = None,
    ) -> "ArticleContext":
        """Return a copy containing only the provided chunk sequence."""

        kwargs: dict[str, Any] = {}
        if best_score is not None:
            kwargs["best_score"] = best_score
        if best_recency is not None:
            kwargs["best_recency"] = best_recency
        return replace(self, chunks=list(chunks), **kwargs)


@dataclass(slots=True)
class ChatContext:
    """Aggregated context ready to feed into an LLM prompt."""

    articles: list[ArticleContext]
    total_chunks: int
    total_tokens: int

    @property
    def unique_sites(self) -> list[str]:
        """Sites represented in the context, sorted for stability."""

        seen = {article.site for article in self.articles if article.site}
        return sorted(seen)


@dataclass(slots=True)
class _ArticleBuilder:
    """Mutable helper that accumulates chunk and metadata for an article."""

    article_id: str
    order: int
    site: str | None = None
    url: str | None = None
    title: str | None = None
    description: str | None = None
    author: str | None = None
    published_at: str | None = None
    published_at_ts: int | None = None
    indexed_at: str | None = None
    indexed_at_ts: int | None = None
    chunks: list[ChunkContext] = field(default_factory=list)
    best_score: float = float("-inf")
    best_recency: float = 0.0

    def ensure_metadata(self, **metadata: Any) -> None:
        for key, value in metadata.items():
            if value in (None, ""):
                continue
            current = getattr(self, key, None)
            if not current:
                setattr(self, key, value)

    def add_chunk(self, chunk: ChunkContext, *, per_article: int) -> None:
        if len(self.chunks) >= per_article:
            return
        self.chunks.append(chunk)
        if chunk.score > self.best_score:
            self.best_score = chunk.score
            self.best_recency = chunk.recency_weight

    def finalize(self) -> ArticleContext | None:
        if not self.chunks:
            return None
        best_score = 0.0 if self.best_score == float("-inf") else self.best_score
        return ArticleContext(
            article_id=self.article_id,
            site=self.site,
            url=self.url,
            title=self.title,
            description=self.description,
            author=self.author,
            published_at=self.published_at,
            published_at_ts=self.published_at_ts,
            indexed_at=self.indexed_at,
            indexed_at_ts=self.indexed_at_ts,
            best_score=best_score,
            best_recency=self.best_recency,
            chunks=list(self.chunks),
        )


def build_chat_context(
    client: "QdrantClient",
    query_vector: Sequence[float],
    *,
    filters: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    chunk_limit: int = DEFAULT_CHUNK_LIMIT,
    per_article: int = DEFAULT_PER_ARTICLE,
    article_limit: int = DEFAULT_ARTICLE_LIMIT,
    candidate_multiplier: int = DEFAULT_CHUNK_CANDIDATE_MULTIPLIER,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    min_articles: int = DEFAULT_MIN_ARTICLES,
    min_sites: int = DEFAULT_MIN_SITES,
) -> ChatContext:
    """Harvest a balanced chunk set suited for conversational answers."""

    if chunk_limit <= 0 or per_article <= 0:
        return ChatContext(articles=[], total_chunks=0, total_tokens=0)

    candidate_limit = max(chunk_limit * candidate_multiplier, chunk_limit)
    builders: dict[str, _ArticleBuilder] = {}

    _accumulate_chunk_hits(
        builders,
        search_chunks(
            client,
            query_vector,
            limit=candidate_limit,
            filters=filters,
            now=now,
        ),
        per_article=per_article,
        start_order=0,
    )

    if builders:
        site_count = {builder.site for builder in builders.values() if builder.site}
    else:
        site_count = set()

    if (
        len(builders) < max(min_articles, 1)
        or len(site_count) < max(min_sites, 1)
    ) and article_limit > 0:
        _augment_with_articles(
            builders,
            client,
            query_vector,
            filters=filters,
            now=now,
            per_article=per_article,
            article_limit=article_limit,
        )

    articles = _finalize_articles(builders)
    if not articles:
        return ChatContext(articles=[], total_chunks=0, total_tokens=0)

    diversified = _prioritize_site_diversity(articles, min_sites=min_sites)
    limited_by_chunks = _limit_chunks_per_window(diversified, chunk_limit)
    window = _apply_token_limit(limited_by_chunks, max_tokens=max_tokens)

    total_chunks = sum(len(article.chunks) for article in window)
    total_tokens = sum(chunk.token_count for article in window for chunk in article.chunks)

    return ChatContext(
        articles=window,
        total_chunks=total_chunks,
        total_tokens=total_tokens,
    )


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    words = text.count(" ") + 1
    chars = len(text)
    approximate = max(chars // 4, words)
    return max(approximate, 1)


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):  # noqa: BLE001
        return None


def _extract_meta_from_chunk(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "site": payload.get("site"),
        "url": payload.get("url"),
        "title": payload.get("article_title") or payload.get("title"),
        "description": payload.get("article_description") or payload.get("description"),
        "author": payload.get("author"),
        "published_at": payload.get("published_at"),
        "published_at_ts": _safe_int(payload.get("published_at_ts")),
        "indexed_at": payload.get("indexed_at"),
        "indexed_at_ts": _safe_int(payload.get("indexed_at_ts")),
    }


def _extract_meta_from_article(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "site": payload.get("site"),
        "url": payload.get("url"),
        "title": payload.get("title"),
        "description": payload.get("description"),
        "author": payload.get("author"),
        "published_at": payload.get("published_at"),
        "published_at_ts": _safe_int(payload.get("published_at_ts")),
        "indexed_at": payload.get("indexed_at"),
        "indexed_at_ts": _safe_int(payload.get("indexed_at_ts")),
    }


def _chunk_context_from_result(result: SearchResult) -> ChunkContext | None:
    payload = result.payload or {}
    article_id = str(payload.get("article_id") or "").strip()
    content = payload.get("content")
    if not article_id or not content:
        return None

    chunk_ix = payload.get("chunk_ix")
    try:
        chunk_ix_value = int(chunk_ix)
    except (TypeError, ValueError):  # noqa: BLE001
        chunk_ix_value = None

    return ChunkContext(
        chunk_id=str(result.id),
        article_id=article_id,
        content=str(content),
        chunk_ix=chunk_ix_value,
        site=payload.get("site"),
        url=payload.get("url"),
        published_at=payload.get("published_at"),
        published_at_ts=_safe_int(payload.get("published_at_ts")),
        indexed_at=payload.get("indexed_at"),
        indexed_at_ts=_safe_int(payload.get("indexed_at_ts")),
        score=result.combined_score,
        vector_score=result.vector_score,
        recency_weight=result.recency_weight,
        token_count=_estimate_tokens(str(content)),
    )


def _accumulate_chunk_hits(
    builders: dict[str, _ArticleBuilder],
    hits: Sequence[SearchResult],
    *,
    per_article: int,
    start_order: int,
) -> int:
    order = start_order
    for result in hits:
        chunk = _chunk_context_from_result(result)
        if chunk is None:
            continue
        builder = builders.get(chunk.article_id)
        metadata = _extract_meta_from_chunk(result.payload)
        if builder is None:
            builder = _ArticleBuilder(article_id=chunk.article_id, order=order)
            builders[chunk.article_id] = builder
            order += 1
        builder.ensure_metadata(**metadata)
        builder.add_chunk(chunk, per_article=per_article)
    return order


def _augment_with_articles(
    builders: dict[str, _ArticleBuilder],
    client: "QdrantClient",
    query_vector: Sequence[float],
    *,
    filters: Mapping[str, Any] | None,
    now: datetime | None,
    per_article: int,
    article_limit: int,
) -> None:
    article_hits = search_articles(
        client,
        query_vector,
        limit=article_limit,
        filters=filters,
        now=now,
    )

    missing_ids: list[str] = []
    order = len(builders)

    for result in article_hits:
        payload = result.payload or {}
        article_id = str(payload.get("doc_id") or result.id or "").strip()
        if not article_id:
            continue
        metadata = _extract_meta_from_article(payload)
        builder = builders.get(article_id)
        if builder is None:
            builder = _ArticleBuilder(article_id=article_id, order=order)
            builders[article_id] = builder
            order += 1
        builder.ensure_metadata(**metadata)
        if len(builder.chunks) < per_article:
            missing_ids.append(article_id)

    if not missing_ids:
        return

    extra_filters = dict(filters or {})
    extra_filters["article_id"] = missing_ids
    extra_limit = max(len(missing_ids) * per_article * 2, per_article)

    _accumulate_chunk_hits(
        builders,
        search_chunks(
            client,
            query_vector,
            limit=extra_limit,
            filters=extra_filters,
            now=now,
        ),
        per_article=per_article,
        start_order=order,
    )


def _finalize_articles(builders: Mapping[str, _ArticleBuilder]) -> list[ArticleContext]:
    finalized: list[tuple[float, int, ArticleContext]] = []
    for builder in builders.values():
        context = builder.finalize()
        if context is None:
            continue
        finalized.append((-context.best_score, builder.order, context))
    finalized.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in finalized]


def _prioritize_site_diversity(
    articles: Sequence[ArticleContext],
    *,
    min_sites: int,
) -> list[ArticleContext]:
    if min_sites <= 1:
        return list(articles)

    chosen: list[ArticleContext] = []
    remaining: list[ArticleContext] = []
    seen: set[str] = set()

    for article in articles:
        site = article.site or ""
        if len(seen) < min_sites and site and site not in seen:
            chosen.append(article)
            seen.add(site)
        else:
            remaining.append(article)

    chosen.extend(remaining)
    return chosen


def _limit_chunks_per_window(
    articles: Sequence[ArticleContext],
    chunk_limit: int,
) -> list[ArticleContext]:
    if chunk_limit <= 0:
        return []

    per_article_counts: dict[str, int] = {}
    selected = 0

    while selected < chunk_limit:
        added = False
        for article in articles:
            count = per_article_counts.get(article.article_id, 0)
            if count < len(article.chunks):
                per_article_counts[article.article_id] = count + 1
                selected += 1
                added = True
                if selected >= chunk_limit:
                    break
        if not added:
            break

    trimmed: list[ArticleContext] = []
    for article in articles:
        count = per_article_counts.get(article.article_id, 0)
        if count:
            trimmed_chunks = article.chunks[:count]
            trimmed.append(article.trimmed(trimmed_chunks, best_score=article.best_score, best_recency=article.best_recency))
    return trimmed


def _apply_token_limit(
    articles: Sequence[ArticleContext],
    *,
    max_tokens: int,
) -> list[ArticleContext]:
    if max_tokens <= 0:
        return list(articles)

    total = 0
    limited: list[ArticleContext] = []

    for article in articles:
        kept: list[ChunkContext] = []
        for chunk in article.chunks:
            tokens = max(chunk.token_count, 1)
            if total and total + tokens > max_tokens:
                break
            kept.append(chunk)
            total += tokens
            if total >= max_tokens:
                break
        if kept:
            limited.append(article.trimmed(kept, best_score=article.best_score, best_recency=article.best_recency))
        if total >= max_tokens:
            break

    return limited


__all__ = [
    "ChunkContext",
    "ArticleContext",
    "ChatContext",
    "build_chat_context",
]
