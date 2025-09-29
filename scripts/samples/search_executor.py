#!/usr/bin/env python3
"""Reusable helper to execute intent plans against Qdrant."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

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
from src.search.qdrant_search import _build_filter, _timestamp_from_payload, _parse_datetime  # type: ignore
from src.search.context_builder import build_chat_context
from pipeline.qdrant_ops import ARTICLES_COLLECTION, CHUNKS_COLLECTION

RECENCY_INFO_FIELDS = ["published_at", "indexed_at", "published_at_ts", "indexed_at_ts"]

_EMPTY = object()


def _round_if_number(value: Any, digits: int = 6) -> Any:
    if isinstance(value, (int, float)):
        return round(float(value), digits)
    return value


def _clean_value(value: Any) -> Any:
    if value is None:
        return _EMPTY
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return _EMPTY
        return trimmed
    if isinstance(value, Mapping):
        cleaned = {}
        for key, nested_value in value.items():
            normalized = _clean_value(nested_value)
            if normalized is _EMPTY:
                continue
            cleaned[key] = normalized
        if not cleaned:
            return _EMPTY
        return cleaned
    if isinstance(value, (list, tuple, set)):
        cleaned_items = []
        for item in value:
            normalized = _clean_value(item)
            if normalized is _EMPTY:
                continue
            cleaned_items.append(normalized)
        if not cleaned_items:
            return _EMPTY
        # Preserve list semantics; tuples/sets are converted to lists for JSON.
        return cleaned_items
    return value


def _clean_mapping(mapping: Mapping[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in mapping.items():
        normalized = _clean_value(value)
        if normalized is _EMPTY:
            continue
        cleaned[key] = normalized
    return cleaned

DEFAULT_ARTICLE_TOPK = 10
DEFAULT_CHUNK_TOPK = 10
DEFAULT_LATEST_PER_SITE = 5
DEFAULT_BACKGROUND_TOPK = 20


def normalize_payload_fields(payload: Mapping[str, Any], desired_fields: Iterable[str]) -> Dict[str, Any]:
    extracted: Dict[str, Any] = {}
    for field in desired_fields:
        if field not in payload:
            continue
        extracted[field] = payload[field]
    for field in RECENCY_INFO_FIELDS:
        if field not in extracted and field in payload:
            extracted[field] = payload[field]
    return extracted


def serialize_result(result: SearchResult, fields: Iterable[str]) -> Dict[str, Any]:
    payload = normalize_payload_fields(dict(result.payload), fields)
    payload_ts = payload.get("published_at_ts") or payload.get("indexed_at_ts")
    payload.pop("published_at_ts", None)
    payload.pop("indexed_at_ts", None)
    payload.pop("indexed_at", None)
    payload = _clean_mapping(payload)
    result_payload: Dict[str, Any] = {"id": result.id}
    scores = _clean_mapping(
        {
            "vector": _round_if_number(result.vector_score),
            "recency": _round_if_number(result.recency_weight),
            "combined": _round_if_number(result.combined_score),
        }
    )
    if scores:
        result_payload["scores"] = scores
    if payload_ts is not None:
        try:
            result_payload["timestamp"] = int(payload_ts)
        except (TypeError, ValueError):
            pass
    if payload:
        result_payload["payload"] = payload
    return result_payload


def serialize_context(context) -> Dict[str, Any]:
    articles: List[Dict[str, Any]] = []
    for article in context.articles:
        article_payload: Dict[str, Any] = _clean_mapping(
            {
                "id": article.article_id,
                "site": article.site,
                "url": article.url,
                "title": article.title,
                "description": article.description,
                "author": article.author,
                "published_at": article.published_at,
            }
        )
        chunk_entries: List[Dict[str, Any]] = []
        for chunk in article.chunks:
            chunk_payload = _clean_mapping(
                {
                    "chunk_ix": chunk.chunk_ix,
                    "score": _round_if_number(chunk.score),
                    "recency": _round_if_number(chunk.recency_weight),
                    "snippet": _make_snippet(chunk.content),
                }
            )
            if chunk_payload:
                chunk_entries.append(chunk_payload)
        if chunk_entries:
            article_payload["chunks"] = chunk_entries
        if article_payload:
            articles.append(article_payload)
    return _clean_mapping(
        {
            "total_chunks": context.total_chunks,
            "total_tokens": context.total_tokens,
            "unique_sites": context.unique_sites,
            "articles": articles,
        }
    )


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
    return {
        "site": clean_filter_list(raw.get("site")),
        "base_url": clean_filter_list(raw.get("base_url")),
        "url": clean_filter_list(raw.get("url")),
        "lang": clean_filter_list(raw.get("lang")),
        "author": clean_filter_list(raw.get("author")),
        "article_id": clean_filter_list(raw.get("article_id")),
        "date_from": str(raw.get("date_from", "")).strip(),
        "date_to": str(raw.get("date_to", "")).strip(),
    }


def drop_empty_filters(filters: Mapping[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in filters.items():
        if isinstance(value, list) and not value:
            continue
        if isinstance(value, str) and not value:
            continue
        cleaned[key] = value
    return cleaned


def _date_bounds(filters: Mapping[str, Any]) -> tuple[Optional[int], Optional[int]]:
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    gte_ts: Optional[int] = None
    lte_ts: Optional[int] = None
    if date_from:
        try:
            gte_ts = _parse_datetime(str(date_from))
        except Exception:  # noqa: BLE001
            gte_ts = None
    if date_to:
        try:
            lte_ts = _parse_datetime(str(date_to), end_of_day=True)
        except Exception:  # noqa: BLE001
            lte_ts = None
    return gte_ts, lte_ts


def _filter_by_date(results: List[Dict[str, Any]], filters: Mapping[str, Any]) -> List[Dict[str, Any]]:
    gte_ts, lte_ts = _date_bounds(filters)
    if gte_ts is None and lte_ts is None:
        for item in results:
            if isinstance(item, dict):
                item.pop("timestamp", None)
        return results
    filtered: List[Dict[str, Any]] = []
    for item in results:
        ts = item.get("timestamp")
        if ts is None:
            payload = item.get("payload", {})
            if isinstance(payload, Mapping):
                ts = payload.get("published_at_ts") or payload.get("indexed_at_ts")
        if not isinstance(ts, (int, float)):
            filtered.append(item)
            continue
        if gte_ts is not None and ts < gte_ts:
            continue
        if lte_ts is not None and ts > lte_ts:
            continue
        filtered.append(item)
    for item in filtered:
        if isinstance(item, dict):
            item.pop("timestamp", None)
    return filtered


def _make_snippet(text: Optional[str], limit: int = 320) -> str:
    if not text:
        return ""
    out = " ".join(str(text).split())
    if len(out) <= limit:
        return out
    return out[: limit].rstrip() + "…"


def ensure_clients(qdrant_client=None, openai_client=None):
    load_dotenv()
    if qdrant_client is None:
        qdrant_client = get_client()
    if openai_client is None:
        openai_client = OpenAI()
    return qdrant_client, openai_client


def get_embedding(client: OpenAI, text: str) -> List[float]:
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


def execute_latest_by_site(qdrant_client, filters: Dict[str, Any], per_site: int):
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
        output[site] = _filter_by_date(output[site], filters)
    return output


def execute_search_articles(qdrant_client, embedding: List[float], filters: Dict[str, Any], top_k: int):
    cleaned_filters = drop_empty_filters(filters)
    limit = top_k or DEFAULT_ARTICLE_TOPK
    hits = search_articles(
        qdrant_client,
        embedding,
        limit=limit,
        filters=cleaned_filters if cleaned_filters else None,
        now=datetime.now(timezone.utc),
    )
    results = [serialize_result(hit, ["title", "url", "site", "author", "published_at"]) for hit in hits]
    return _filter_by_date(results, filters)


def execute_search_chunks(
    qdrant_client,
    embedding: List[float],
    filters: Dict[str, Any],
    top_k: int,
    exact_phrase: bool,
    phrase: str,
):
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
    results = [serialize_result(hit, ["url", "content", "site", "author", "published_at"]) for hit in hits[:limit]]
    return _filter_by_date(results, filters)


def execute_filter_only(qdrant_client, filters: Dict[str, Any], top_k: int, collection: str):
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
    fields = (
        ["title", "url", "site", "author", "published_at"]
        if collection == ARTICLES_COLLECTION
        else ["url", "content", "site", "author", "published_at"]
    )
    serialised = [serialize_result(result, fields) for result in results[: (top_k or DEFAULT_ARTICLE_TOPK)]]
    return _filter_by_date(serialised, filters)


def build_context(qdrant_client, embedding: Optional[List[float]], filters: Dict[str, Any], top_k: int):
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
    return serialize_context(context)


def execute_plan(
    query: str,
    plan: Mapping[str, Any],
    *,
    qdrant_client=None,
    openai_client=None,
) -> Dict[str, Any]:
    qdrant_client, openai_client = ensure_clients(qdrant_client, openai_client)

    intent = str(plan.get("intent"))
    filters = sanitize_filters(plan.get("filters", {}))
    top_k = int(plan.get("topK", 0) or 0)
    per_site = int(plan.get("per_site", 0) or 0)
    exact_phrase = bool(plan.get("exact_phrase", False))
    query_text = str(plan.get("query", "")).strip()

    needs_embedding = intent in {
        "search_articles",
        "search_chunks",
        "summarize",
        "compare_viewpoints",
        "backgrounder",
    } and bool(query_text)

    embedding: Optional[List[float]] = None
    if needs_embedding:
        embedding = get_embedding(openai_client, query)

    context: Optional[Dict[str, Any]] = None

    if intent == "latest_by_site":
        data = execute_latest_by_site(qdrant_client, filters, per_site)
        return {"data": data, "context": context}

    if intent == "filter_only_articles":
        data = execute_filter_only(qdrant_client, filters, top_k, ARTICLES_COLLECTION)
        return {"data": data, "context": context}

    if intent == "filter_only_chunks":
        data = execute_filter_only(qdrant_client, filters, top_k or DEFAULT_CHUNK_TOPK, CHUNKS_COLLECTION)
        return {"data": data, "context": context}

    if intent == "search_articles":
        if not embedding:
            data = execute_filter_only(qdrant_client, filters, top_k, ARTICLES_COLLECTION)
            return {"data": data, "context": context}
        data = execute_search_articles(qdrant_client, embedding, filters, top_k)
        return {"data": data, "context": context}

    if intent == "search_chunks":
        if not embedding:
            data = execute_filter_only(qdrant_client, filters, top_k or DEFAULT_CHUNK_TOPK, CHUNKS_COLLECTION)
            return {"data": data, "context": context}
        phrase = query_text if exact_phrase else ""
        data = execute_search_chunks(qdrant_client, embedding, filters, top_k, exact_phrase, phrase)
        return {"data": data, "context": context}

    if intent == "summarize":
        if embedding:
            data = execute_search_articles(qdrant_client, embedding, filters, top_k or DEFAULT_ARTICLE_TOPK)
            context = build_context(qdrant_client, embedding, filters, top_k or DEFAULT_ARTICLE_TOPK)
            return {"data": data, "context": context}
        data = execute_filter_only(qdrant_client, filters, top_k, ARTICLES_COLLECTION)
        return {"data": data, "context": context}

    if intent == "compare_viewpoints":
        if embedding:
            sites = [s for s in filters.get("site", []) if s]
            if sites:
                data: Dict[str, Any] = {}
                for site in sites:
                    site_filters = dict(filters)
                    site_filters["site"] = [site]
                    data[site] = execute_search_articles(qdrant_client, embedding, site_filters, top_k or DEFAULT_ARTICLE_TOPK)
                context = build_context(qdrant_client, embedding, filters, top_k or DEFAULT_ARTICLE_TOPK)
                return {"data": data, "context": context}
            data = execute_search_articles(qdrant_client, embedding, filters, top_k or DEFAULT_ARTICLE_TOPK)
            context = build_context(qdrant_client, embedding, filters, top_k or DEFAULT_ARTICLE_TOPK)
            return {"data": data, "context": context}
        data = execute_filter_only(qdrant_client, filters, top_k or DEFAULT_ARTICLE_TOPK, ARTICLES_COLLECTION)
        return {"data": data, "context": context}

    if intent == "backgrounder":
        if embedding:
            data = execute_search_articles(qdrant_client, embedding, filters, top_k or DEFAULT_BACKGROUND_TOPK)
            context = build_context(qdrant_client, embedding, filters, top_k or DEFAULT_BACKGROUND_TOPK)
            return {"data": data, "context": context}
        data = execute_filter_only(qdrant_client, filters, top_k or DEFAULT_BACKGROUND_TOPK, ARTICLES_COLLECTION)
        return {"data": data, "context": context}

    raise ValueError(f"Intent desconocido: {intent}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run a single plan against Qdrant")
    parser.add_argument("plan", help="JSON string or path to JSON file with the plan")
    parser.add_argument("query", help="User query associated to the plan")
    args = parser.parse_args()

    plan_input = Path(args.plan)
    if plan_input.exists():
        plan_data = json.loads(plan_input.read_text())
    else:
        plan_data = json.loads(args.plan)

    result = execute_plan(args.query, plan_data)
    print(json.dumps(result, indent=2, ensure_ascii=False))
