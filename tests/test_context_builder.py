from datetime import datetime

from search.context_builder import build_chat_context
from search.qdrant_search import SearchResult


class DummyClient:
    pass


def _chunk_result(
    article_id: str,
    chunk_ix: int,
    *,
    site: str = "site-a",
    url: str | None = None,
    content: str | None = None,
    combined_score: float = 0.8,
    vector_score: float = 0.7,
    recency_weight: float = 0.6,
    published_ts: int = 1700000000,
) -> SearchResult:
    payload = {
        "article_id": article_id,
        "site": site,
        "url": url or f"https://{site}.example/{article_id}",
        "chunk_ix": chunk_ix,
        "content": content or f"content {article_id}-{chunk_ix}",
        "published_at": datetime.utcfromtimestamp(published_ts).isoformat() + "Z",
        "published_at_ts": published_ts,
        "indexed_at": datetime.utcfromtimestamp(published_ts + 3600).isoformat() + "Z",
        "indexed_at_ts": published_ts + 3600,
        "article_title": f"Title {article_id}",
        "article_description": f"Desc {article_id}",
        "author": "Reporter",
    }
    return SearchResult(
        id=f"{article_id}:{chunk_ix}",
        payload=payload,
        vector_score=vector_score,
        recency_weight=recency_weight,
        combined_score=combined_score,
    )


def _article_result(
    article_id: str,
    *,
    site: str = "site-b",
    url: str | None = None,
    combined_score: float = 0.75,
) -> SearchResult:
    payload = {
        "doc_id": article_id,
        "site": site,
        "url": url or f"https://{site}.example/{article_id}",
        "title": f"Title {article_id}",
        "description": f"Desc {article_id}",
        "author": "Reporter",
        "published_at": "2024-05-01T10:00:00Z",
        "published_at_ts": 1714557600,
        "indexed_at": "2024-05-01T11:00:00Z",
        "indexed_at_ts": 1714561200,
    }
    return SearchResult(
        id=article_id,
        payload=payload,
        vector_score=combined_score,
        recency_weight=0.5,
        combined_score=combined_score,
    )


def test_build_chat_context_basic(monkeypatch):
    chunk_hits = [
        _chunk_result("a1", 0, combined_score=0.95),
        _chunk_result("a1", 1, combined_score=0.9),
        _chunk_result("b2", 0, combined_score=0.85, site="site-b"),
        _chunk_result("b2", 1, combined_score=0.82, site="site-b"),
    ]

    monkeypatch.setattr("search.context_builder.search_chunks", lambda *args, **kwargs: chunk_hits)
    monkeypatch.setattr("search.context_builder.search_articles", lambda *args, **kwargs: [])

    ctx = build_chat_context(
        DummyClient(),
        [0.1, 0.2, 0.3],
        chunk_limit=4,
        per_article=2,
        min_articles=1,
        min_sites=1,
        max_tokens=10_000,
    )

    assert ctx.total_chunks == 4
    assert len(ctx.articles) == 2
    assert ctx.articles[0].chunks[0].content.startswith("content a1-0")
    assert set(ctx.unique_sites) == {"site-a", "site-b"}


def test_round_robin_chunk_limit(monkeypatch):
    chunk_hits = [
        _chunk_result("a1", 0, combined_score=0.95),
        _chunk_result("a1", 1, combined_score=0.9),
        _chunk_result("a1", 2, combined_score=0.85),
        _chunk_result("b2", 0, combined_score=0.8, site="site-b"),
    ]

    monkeypatch.setattr("search.context_builder.search_chunks", lambda *args, **kwargs: chunk_hits)
    monkeypatch.setattr("search.context_builder.search_articles", lambda *args, **kwargs: [])

    ctx = build_chat_context(
        DummyClient(),
        [0.1, 0.2, 0.3],
        chunk_limit=3,
        per_article=3,
        min_articles=1,
        min_sites=1,
        max_tokens=10_000,
    )

    assert ctx.total_chunks == 3
    article_summary = {article.article_id: len(article.chunks) for article in ctx.articles}
    assert article_summary["a1"] == 2
    assert article_summary["b2"] == 1


def test_fallback_expands_missing_article(monkeypatch):
    first_call_chunks = [_chunk_result("a1", 0, combined_score=0.9)]

    def fake_search_chunks(client, vector, *, limit, filters=None, now=None):
        if filters and filters.get("article_id"):
            return [_chunk_result("b2", 0, combined_score=0.88, site="site-b")]
        return list(first_call_chunks)

    monkeypatch.setattr("search.context_builder.search_chunks", fake_search_chunks)
    monkeypatch.setattr(
        "search.context_builder.search_articles",
        lambda *args, **kwargs: [_article_result("b2", site="site-b")],
    )

    ctx = build_chat_context(
        DummyClient(),
        [0.5, 0.4, 0.3],
        chunk_limit=4,
        per_article=2,
        min_articles=2,
        min_sites=1,
        max_tokens=10_000,
    )

    assert ctx.total_chunks == 2
    assert {article.article_id for article in ctx.articles} == {"a1", "b2"}


def test_token_limit_truncates(monkeypatch):
    big_text = "word " * 200
    chunk_hits = [
        _chunk_result("a1", 0, content=big_text, combined_score=0.95),
        _chunk_result("a1", 1, content=big_text, combined_score=0.9),
    ]

    monkeypatch.setattr("search.context_builder.search_chunks", lambda *args, **kwargs: chunk_hits)
    monkeypatch.setattr("search.context_builder.search_articles", lambda *args, **kwargs: [])

    ctx = build_chat_context(
        DummyClient(),
        [0.1, 0.2, 0.3],
        chunk_limit=5,
        per_article=3,
        min_articles=1,
        min_sites=1,
        max_tokens=150,
    )

    assert ctx.total_chunks == 1
    assert len(ctx.articles) == 1
    assert len(ctx.articles[0].chunks) == 1

