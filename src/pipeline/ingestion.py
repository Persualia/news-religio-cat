"""Daily ingestion pipeline orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import logging
from typing import Callable, Iterable, Optional, Sequence, TYPE_CHECKING
import time

from collections import defaultdict

from vector_client import get_client

if TYPE_CHECKING:  # pragma: no cover
    from qdrant_client import QdrantClient

from chunking import chunk_text
from embeddings import embed_texts
from models import Article, Chunk, url_to_id
from scraping import BaseScraper, instantiate_scrapers

from .qdrant_ops import (
    ARTICLES_COLLECTION,
    CHUNKS_COLLECTION,
    ensure_collections,
    index_articles,
    index_chunks,
    find_existing_article_ids,
)
from .summary import post_summary, summarize_articles

Embedder = Callable[[Sequence[str]], list[list[float]]]
Summarizer = Callable[[Sequence[Article]], str]
SummaryPoster = Callable[[str], object]


logger = logging.getLogger(__name__)


def _average_vector(vectors: Sequence[list[float]]) -> list[float]:
    if not vectors:
        return []
    length = len(vectors)
    if length == 1:
        return list(vectors[0])
    accum = [0.0] * len(vectors[0])
    for vec in vectors:
        for idx, value in enumerate(vec):
            accum[idx] += value
    return [value / length for value in accum]


@dataclass
class PipelineResult:
    articles_indexed: int
    chunks_indexed: int
    summary: str


class DailyPipeline:
    def __init__(
        self,
        *,
        scrapers: Optional[Sequence[BaseScraper]] = None,
        client: Optional["QdrantClient"] = None,
        embedder: Optional[Embedder] = None,
        summarizer: Optional[Summarizer] = None,
        summary_poster: Optional[SummaryPoster] = None,
    ) -> None:
        self._scrapers = list(scrapers) if scrapers else instantiate_scrapers()
        self._client = client
        self._embedder = embedder or embed_texts
        self._summarizer = summarizer or summarize_articles
        self._summary_poster = summary_poster or post_summary

    def run(
        self,
        *,
        now: Optional[datetime] = None,
        limit_per_site: Optional[int] = None,
        dry_run: bool = False,
        skip_indexing: bool = False,
    ) -> PipelineResult:
        mode_label = "DRY-RUN" if dry_run else "LIVE"
        if skip_indexing and not dry_run:
            mode_label = f"{mode_label} (NO-INDEX)"
        header = f"{' ' + mode_label + ' PIPELINE START ':=^80}"
        logger.info(header)
        logger.info(
            "Parameters: limit_per_site=%s, now=%s, skip_indexing=%s",
            limit_per_site if limit_per_site is not None else "all",
            now.isoformat() if now else "auto",
            skip_indexing,
        )

        client: Optional["QdrantClient"] = None
        articles_collection = ARTICLES_COLLECTION
        chunks_collection = CHUNKS_COLLECTION

        if not dry_run and not skip_indexing:
            client = self._client or get_client()
            ensure_collections(client)
            logger.info(
                "Qdrant collections ready: articles=%s chunks=%s",
                articles_collection,
                chunks_collection,
            )
        elif dry_run:
            logger.info("Running pipeline in dry-run mode (no indexing or OpenAI calls).")
            articles_collection = "articles-dry-run"
            chunks_collection = "chunks-dry-run"
        else:  # skip_indexing without dry_run
            logger.info("Vector indexing disabled by flag; skipping Qdrant setup.")
            articles_collection = "articles-skipped"
            chunks_collection = "chunks-skipped"

        articles: list[Article] = []
        for scraper in self._scrapers:
            logger.debug("Scraping site %s", getattr(scraper, "site_id", type(scraper).__name__))

            if isinstance(scraper, BaseScraper):
                # Phase 1: listing + precheck existing (when vector store client available)
                try:
                    listing_soup = scraper._get_soup(scraper.listing_url)
                    raw_urls = list(scraper.extract_article_urls(listing_soup))
                    # Normalize to absolute + canonical form as scrapers would
                    candidate_urls = list(dict.fromkeys(scraper._normalize_url(u) for u in raw_urls))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed listing for %s: %s", scraper.site_id, exc)
                    candidate_urls = []

                # Apply precheck to skip existing docs across months when indexing is enabled
                to_fetch_urls: list[str] = candidate_urls
                if client is not None and candidate_urls:
                    ids = [url_to_id(u) for u in candidate_urls]
                    existing = find_existing_article_ids(client, ids)
                    if existing:
                        logger.debug(
                            "%s: %d/%d URLs already indexed; skipping.",
                            scraper.site_id,
                            len(existing),
                            len(ids),
                        )
                    idset = set(existing)
                    to_fetch_urls = [u for u, i in zip(candidate_urls, ids, strict=False) if i not in idset]

                # Respect limit AFTER filtering, to process up to N new items
                if limit_per_site is not None:
                    to_fetch_urls = to_fetch_urls[: limit_per_site]

                # Phase 2: fetch + parse remaining URLs
                for url in to_fetch_urls:
                    try:
                        soup = scraper._get_soup(url)
                        article = scraper.parse_article(soup, url)
                        articles.append(article)
                        # Throttle per scraper settings
                        time.sleep(getattr(scraper, "_throttle_seconds", 0))
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Failed to parse %s: %s", url, exc)
            else:
                # Fallback for simple stub scrapers used in tests
                try:
                    articles.extend(scraper.scrape(limit=limit_per_site))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Fallback scrape failed for %s: %s", type(scraper).__name__, exc)

        deduped_articles = list({article.doc_id: article for article in articles}.values())
        logger.info("Scraped %d articles (deduped).", len(deduped_articles))

        if dry_run:
            for article in deduped_articles:
                doc = article.to_document()
                # Create a truncated version for logging to avoid truncation
                log_doc = {}
                for key, value in doc.items():
                    if isinstance(value, str) and len(value) > 200:
                        log_doc[key] = value[:200] + "..."
                    else:
                        log_doc[key] = value
                logger.info(
                    "Article document: %s",
                    json.dumps(log_doc, ensure_ascii=False, sort_keys=True, indent=2),
                )
            logger.info("Dry-run summary: %d article(s) scraped", len(deduped_articles))
            footer = f"{' ' + mode_label + ' PIPELINE END ':=^80}"
            logger.info(footer)
            return PipelineResult(
                articles_indexed=0,
                chunks_indexed=0,
                summary="Dry run: summary not generated",
            )

        chunk_docs: list[Chunk] = []
        article_vectors: dict[str, list[float]] = {}

        if not skip_indexing:
            chunk_inputs: list[tuple[Article, int, str]] = []
            for article in deduped_articles:
                article_chunks = chunk_text(article.content)
                if not article_chunks:
                    fallback_parts = [article.title, article.description, article.content]
                    fallback_text = "\n\n".join(part for part in fallback_parts if part)
                    if not fallback_text:
                        fallback_text = article.url
                    article_chunks = [fallback_text]

                if article_chunks:
                    enriched_first = "\n\n".join(
                        part
                        for part in (article.title, article.description, article_chunks[0])
                        if part
                    )
                    article_chunks[0] = enriched_first

                logger.debug("Generated %d chunk(s) for %s", len(article_chunks), article.url)
                for ix, chunk in enumerate(article_chunks):
                    chunk_inputs.append((article, ix, chunk))

            chunk_vectors = (
                self._embedder([chunk for (_, _, chunk) in chunk_inputs]) if chunk_inputs else []
            )

            chunk_docs = [
                Chunk(article=article, chunk_ix=ix, content=chunk, content_vec=vector)
                for (article, ix, chunk), vector in zip(chunk_inputs, chunk_vectors, strict=True)
            ]

            vectors_by_article: dict[str, list[list[float]]] = defaultdict(list)
            for chunk_doc in chunk_docs:
                vectors_by_article[chunk_doc.article.doc_id].append(chunk_doc.content_vec)
            article_vectors = {}
            for article in deduped_articles:
                vectors = vectors_by_article.get(article.doc_id)
                if vectors:
                    article_vectors[article.doc_id] = _average_vector(vectors)

            if client is not None and chunk_docs:
                index_chunks(client, chunk_docs)
        else:
            logger.info("Skipping chunk embedding/indexing.")

        if deduped_articles and client is not None:
            if article_vectors:
                logger.info(
                    "Prepared vectors for %d/%d articles.",
                    sum(1 for article in deduped_articles if article.doc_id in article_vectors),
                    len(deduped_articles),
                )
                index_articles(client, deduped_articles, article_vectors)
            else:
                logger.info("No article vectors generated; indexing skipped for this run.")
        elif skip_indexing and deduped_articles:
            logger.info("Skipping article indexing (%d items) as requested.", len(deduped_articles))

        summary = self._summarizer(deduped_articles)
        try:
            self._summary_poster(summary)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to post summary: %s", exc)

        result = PipelineResult(
            articles_indexed=len(deduped_articles) if not skip_indexing else 0,
            chunks_indexed=len(chunk_docs) if not skip_indexing else 0,
            summary=summary,
        )

        logger.info(
            "Pipeline summary: articles=%d chunks=%d",
            result.articles_indexed,
            result.chunks_indexed,
        )
        footer = f"{' ' + mode_label + ' PIPELINE END ':=^80}"
        logger.info(footer)

        return result


__all__ = ["DailyPipeline", "PipelineResult"]
