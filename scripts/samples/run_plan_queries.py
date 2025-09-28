#!/usr/bin/env python3
"""Execute generated intent plans against Qdrant."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional

from dotenv import load_dotenv

THIS_FILE = Path(__file__).resolve()
SAMPLES_DIR = THIS_FILE.parent
ROOT = SAMPLES_DIR.parents[1]

import sys

for candidate in (ROOT, ROOT / "src"):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from openai import OpenAI

from src.vector_client import get_client
from src.search.qdrant_search import (
    SearchResult,
    latest_by_site,
    search_articles,
    search_chunks,
)
from src.search.qdrant_search import _build_filter, _timestamp_from_payload  # type: ignore
from src.search.context_builder import ChatContext, build_chat_context
from pipeline.qdrant_ops import ARTICLES_COLLECTION, CHUNKS_COLLECTION

# ---------------------------------------------------------------------------
# Helpers copied/adapted from run_query_samples for consistent output format
# ---------------------------------------------------------------------------

RECENCY_INFO_FIELDS = ["published_at", "indexed_at", "published_at_ts", "indexed_at_ts"]


def normalize_payload_fields(payload: Mapping[str, Any], desired_fields: Iterable[str]) -> Dict[str, Any]:
    extracted = {field: payload.get(field) for field in desired_fields}
    for field in RECENCY_INFO_FIELDS:
        if field not in extracted and field in payload:
            extracted[field] = payload[field]
    return extracted


def serialize_result(result: SearchResult, fields: Iterable[str]) -> Dict[str, Any]:
    payload = normalize_payload_fields(dict(result.payload), fields)
    payload_ts = payload.get("published_at_ts") or payload.get("indexed_at_ts")
    return {
        "id": result.id,
        "vector_score": result.vector_score,
        "recency_weight": result.recency_weight,
        "combined_score": result.combined_score,
        "timestamp": payload_ts,
        "payload": payload,
    }


def serialize_chat_context(context: ChatContext) -> Dict[str, Any]:
    return {
        "total_chunks": context.total_chunks,
        "total_tokens": context.total_tokens,
        "unique_sites": context.unique_sites,
        "articles": [
            {
                "article_id": article.article_id,
                "site": article.site,
                "url": article.url,
                "title": article.title,
                "description": article.description,
                "author": article.author,
                "published_at": article.published_at,
                "published_at_ts": article.published_at_ts,
                "indexed_at": article.indexed_at,
                "indexed_at_ts": article.indexed_at_ts,
                "best_score": article.best_score,
                "best_recency": article.best_recency,
                "chunks": [
                    {
                        "chunk_id": chunk.chunk_id,
                        "chunk_ix": chunk.chunk_ix,
                        "score": chunk.score,
                        "vector_score": chunk.vector_score,
                        "recency_weight": chunk.recency_weight,
                        "token_count": chunk.token_count,
                        "content": chunk.content,
                        "site": chunk.site,
                        "url": chunk.url,
                        "published_at": chunk.published_at,
                        "published_at_ts": chunk.published_at_ts,
                        "indexed_at": chunk.indexed_at,
                        "indexed_at_ts": chunk.indexed_at_ts,
                    }
                    for chunk in article.chunks
                ],
            }
            for article in context.articles
        ],
    }


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------

DEFAULT_ARTICLE_TOPK = 10
DEFAULT_CHUNK_TOPK = 10
DEFAULT_LATEST_PER_SITE = 5
DEFAULT_BACKGROUND_TOPK = 20
CONTEXT_INTENTS = {"summarize", "compare_viewpoints", "backgrounder"}


PLANS_PATH = SAMPLES_DIR / "query_intents.json"
OUTPUT_DIR = SAMPLES_DIR / "executed_plans"


def load_plans(path: Path) -> Dict[str, Dict[str, Any]]:
    data = json.loads(path.read_text())
    plans = data.get("plans")
    if not isinstance(plans, dict):
        raise SystemExit("query_intents.json no contiene 'plans' válidos")
    return plans


def clean_filter_list(values: Optional[Iterable[str]]) -> List[str]:
    if not values:
        return []
    cleaned: List[str] = []
    for item in values:
        if not item:
            continue
        text = str(item).strip()
        if text:
            cleaned.append(text)
    return cleaned


def sanitize_filters(raw: Mapping[str, Any]) -> Dict[str, Any]:
    filters: Dict[str, Any] = {}
    filters["site"] = clean_filter_list(raw.get("site"))
    filters["url"] = clean_filter_list(raw.get("url"))
    filters["lang"] = clean_filter_list(raw.get("lang"))
    filters["author"] = clean_filter_list(raw.get("author"))
    filters["article_id"] = clean_filter_list(raw.get("article_id"))
    filters["date_from"] = str(raw.get("date_from", "")).strip()
    filters["date_to"] = str(raw.get("date_to", "")).strip()
    return filters


def drop_empty_filters(filters: Mapping[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in filters.items():
        if isinstance(value, list) and not value:
            continue
        if isinstance(value, str) and not value:
            continue
        cleaned[key] = value
    return cleaned


def build_context(
    qdrant_client,
    embedding: Optional[List[float]],
    filters: Dict[str, Any],
    top_k: int,
) -> Optional[Dict[str, Any]]:
    if embedding is None:
        return None
    cleaned_filters = drop_empty_filters(filters)
    context = build_chat_context(
        qdrant_client,
        embedding,
        filters=cleaned_filters if cleaned_filters else None,
        now=datetime.now(timezone.utc),
        chunk_limit=max((top_k or DEFAULT_ARTICLE_TOPK) * 4, 20),
        per_article=3,
        article_limit=max(top_k or DEFAULT_ARTICLE_TOPK, 5),
    )
    if not context.articles:
        return None
    return serialize_chat_context(context)


def slugify(text: str) -> str:
    import re

    normalized = (
        re.sub(r"\s+", " ", text.strip().lower())
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or "query"


def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def get_embedding(client: OpenAI, text: str) -> List[float]:
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


def execute_latest_by_site(
    qdrant_client,
    filters: Dict[str, Any],
    per_site: int,
) -> Dict[str, List[Dict[str, Any]]]:
    cleaned_filters = drop_empty_filters(filters)
    per_site = per_site or DEFAULT_LATEST_PER_SITE
    grouped = latest_by_site(
        qdrant_client,
        filters=cleaned_filters if cleaned_filters else None,
        per_site=per_site,
        now=datetime.now(timezone.utc),
    )
    output: Dict[str, List[Dict[str, Any]]] = {}
    for site, results in grouped.items():
        output[site] = [serialize_result(result, ["title", "url", "site", "author", "published_at"]) for result in results]
    return output


def execute_search_articles(
    qdrant_client,
    embedding: List[float],
    filters: Dict[str, Any],
    top_k: int,
) -> List[Dict[str, Any]]:
    cleaned_filters = drop_empty_filters(filters)
    limit = top_k or DEFAULT_ARTICLE_TOPK
    hits = search_articles(
        qdrant_client,
        embedding,
        limit=limit,
        filters=cleaned_filters if cleaned_filters else None,
        now=datetime.now(timezone.utc),
    )
    return [serialize_result(hit, ["title", "url", "site", "author", "published_at"]) for hit in hits]


def execute_search_chunks(
    qdrant_client,
    embedding: List[float],
    filters: Dict[str, Any],
    top_k: int,
    exact_phrase: bool,
    phrase: str,
) -> List[Dict[str, Any]]:
    cleaned_filters = drop_empty_filters(filters)
    limit = top_k or DEFAULT_CHUNK_TOPK
    hits = search_chunks(
        qdrant_client,
        embedding,
        limit=limit * (2 if exact_phrase else 1),
        filters=cleaned_filters if cleaned_filters else None,
        now=datetime.now(timezone.utc),
    )
    if exact_phrase and phrase:
        needle = phrase.lower()
        filtered: List[SearchResult] = []
        for hit in hits:
            content = str(hit.payload.get("content", "")).lower()
            if needle in content:
                filtered.append(hit)
                if len(filtered) >= limit:
                    break
        hits = filtered
    return [serialize_result(hit, ["url", "content", "site", "author", "published_at"]) for hit in hits[:limit]]


def execute_filter_only(
    qdrant_client,
    filters: Dict[str, Any],
    top_k: int,
    collection: str,
) -> List[Dict[str, Any]]:
    cleaned_filters = drop_empty_filters(filters)
    query_filter = _build_filter(cleaned_filters) if cleaned_filters else None
    limit = max(top_k or DEFAULT_ARTICLE_TOPK, 10)
    collected = []
    offset = None
    while len(collected) < limit:
        points, offset = qdrant_client.scroll(
            collection_name=collection,
            scroll_filter=query_filter,
            with_payload=True,
            limit=limit * 2,
            offset=offset,
        )
        if not points:
            break
        collected.extend(points)
        if offset is None:
            break
    results: List[SearchResult] = []
    for point in collected:
        payload = dict(point.payload or {})
        ts = _timestamp_from_payload(payload)
        results.append(
            SearchResult(
                id=str(point.id),
                payload=payload,
                vector_score=0.0,
                recency_weight=0.0,
                combined_score=float(ts),
            )
        )
    results.sort(key=lambda item: _timestamp_from_payload(item.payload), reverse=True)
    return [
        serialize_result(result, ["title", "url", "site", "author", "published_at"] if collection == ARTICLES_COLLECTION else ["url", "content", "site", "author", "published_at"])
        for result in results[: (top_k or DEFAULT_ARTICLE_TOPK)]
    ]


def execute_plan(
    qdrant_client,
    openai_client,
    query_text: str,
    intent: str,
    filters: Dict[str, Any],
    top_k: int,
    per_site: int,
    exact_phrase: bool,
) -> Any:
    query_text = query_text.strip()
    needs_embedding = intent in {
        "search_articles",
        "search_chunks",
        "summarize",
        "compare_viewpoints",
        "backgrounder",
    } and bool(query_text)

    embedding: Optional[List[float]] = None
    if needs_embedding:
        embedding = get_embedding(openai_client, query_text)

    context: Optional[Dict[str, Any]] = None

    if intent == "latest_by_site":
        results = execute_latest_by_site(qdrant_client, filters, per_site)
        return results, context

    if intent == "filter_only_articles":
        results = execute_filter_only(qdrant_client, filters, top_k, ARTICLES_COLLECTION)
        return results, context

    if intent == "filter_only_chunks":
        results = execute_filter_only(qdrant_client, filters, top_k or DEFAULT_CHUNK_TOPK, CHUNKS_COLLECTION)
        return results, context

    if intent == "search_articles":
        if not embedding:
            results = execute_filter_only(qdrant_client, filters, top_k, ARTICLES_COLLECTION)
            return results, context
        results = execute_search_articles(qdrant_client, embedding, filters, top_k)
        return results, context

    if intent == "search_chunks":
        if not embedding:
            results = execute_filter_only(qdrant_client, filters, top_k or DEFAULT_CHUNK_TOPK, CHUNKS_COLLECTION)
            return results, context
        phrase = query_text if exact_phrase else ""
        results = execute_search_chunks(qdrant_client, embedding, filters, top_k, exact_phrase, phrase)
        return results, context

    if intent == "summarize":
        if embedding:
            results = execute_search_articles(qdrant_client, embedding, filters, top_k or DEFAULT_ARTICLE_TOPK)
            context = build_context(qdrant_client, embedding, filters, top_k or DEFAULT_ARTICLE_TOPK)
            return results, context
        results = execute_filter_only(qdrant_client, filters, top_k, ARTICLES_COLLECTION)
        return results, context

    if intent == "compare_viewpoints":
        if embedding:
            sites = [s for s in filters.get("site", []) if s]
            if sites:
                results_by_site: Dict[str, Any] = {}
                for site in sites:
                    site_filters = dict(filters)
                    site_filters["site"] = [site]
                    results_by_site[site] = execute_search_articles(
                        qdrant_client,
                        embedding,
                        site_filters,
                        top_k or DEFAULT_ARTICLE_TOPK,
                    )
                context = build_context(qdrant_client, embedding, filters, top_k or DEFAULT_ARTICLE_TOPK)
                return results_by_site, context
            results = execute_search_articles(qdrant_client, embedding, filters, top_k or DEFAULT_ARTICLE_TOPK)
            context = build_context(qdrant_client, embedding, filters, top_k or DEFAULT_ARTICLE_TOPK)
            return results, context
        results = execute_filter_only(qdrant_client, filters, top_k or DEFAULT_ARTICLE_TOPK, ARTICLES_COLLECTION)
        return results, context

    if intent == "backgrounder":
        if embedding:
            results = execute_search_articles(qdrant_client, embedding, filters, top_k or DEFAULT_BACKGROUND_TOPK)
            context = build_context(qdrant_client, embedding, filters, top_k or DEFAULT_BACKGROUND_TOPK)
            return results, context
        results = execute_filter_only(qdrant_client, filters, top_k or DEFAULT_BACKGROUND_TOPK, ARTICLES_COLLECTION)
        return results, context

    raise ValueError(f"Intent desconocido: {intent}")


def main() -> None:
    load_dotenv()
    plans = load_plans(PLANS_PATH)
    ensure_output_dir(OUTPUT_DIR)

    openai_client = OpenAI()
    qdrant_client = get_client()

    summary: List[Dict[str, Any]] = []

    for idx, (query_text, plan) in enumerate(plans.items(), start=1):
        print(f"[{idx}/{len(plans)}] Ejecutando: {query_text}")
        intent = str(plan.get("intent"))
        filters = sanitize_filters(plan.get("filters", {}))
        top_k = int(plan.get("topK", 0) or 0)
        per_site = int(plan.get("per_site", 0) or 0)
        exact_phrase = bool(plan.get("exact_phrase", False))
        query_value = str(plan.get("query", ""))

        try:
            results, context = execute_plan(
                qdrant_client,
                openai_client,
                query_value,
                intent,
                filters,
                top_k,
                per_site,
                exact_phrase,
            )
            status = "ok"
            error = None
        except Exception as exc:  # noqa: BLE001
            results, context = None, None
            status = "error"
            error = str(exc)
            print(f"  ✖ Error: {error}")

        file_slug = f"{idx:02d}_{slugify(query_text)[:80]}"
        output_path = OUTPUT_DIR / f"{file_slug}.json"
        payload = {
            "query": query_text,
            "plan": plan,
            "status": status,
            "results": {
                "data": results,
                "context": context,
            },
        }
        if error:
            payload["error"] = error
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        summary.append({
            "query": query_text,
            "intent": intent,
            "status": status,
            "result_file": str(output_path.relative_to(ROOT)),
            "error": error,
        })
        if status == "ok":
            print(f"  ✓ Guardado en {output_path}")

    summary_path = OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Resumen guardado en {summary_path}")


if __name__ == "__main__":
    main()
