"""High-level search helpers over Qdrant with filtering and recency weighting."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any, Mapping, Sequence

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from pipeline.qdrant_ops import ARTICLES_COLLECTION, CHUNKS_COLLECTION

HALF_LIFE_HOURS = 36.0
RECENCY_WEIGHT = 0.35
FETCH_MULTIPLIER = 4
SITE_DISCOVERY_LIMIT = 24


@dataclass(frozen=True)
class SearchResult:
    id: str
    payload: Mapping[str, Any]
    vector_score: float
    recency_weight: float
    combined_score: float


def _now_timestamp(now: datetime | None = None) -> int:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return int(current.timestamp())


def _parse_datetime(value: str, *, end_of_day: bool = False) -> int:
    value = value.strip()
    if not value:
        raise ValueError("Empty datetime value")

    try:
        if len(value) == 10:  # YYYY-MM-DD
            year, month, day = map(int, value.split("-"))
            dt = datetime(year, month, day, tzinfo=timezone.utc)
            if end_of_day:
                dt = dt.replace(hour=23, minute=59, second=59, microsecond=999_999)
        else:
            normalized = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
    except ValueError as exc:  # noqa: BLE001
        raise ValueError(f"Invalid datetime format: {value!r}") from exc

    return int(dt.timestamp())


def _filter_match_any(key: str, values: Sequence[str]) -> qmodels.FieldCondition:
    return qmodels.FieldCondition(key=key, match=qmodels.MatchAny(any=list(values)))


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidate = value.strip()
        return [candidate] if candidate else []
    if isinstance(value, Sequence):
        normalized = []
        for item in value:
            if not item:
                continue
            text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized
    return []


def _build_filter(filters: Mapping[str, Any] | None) -> qmodels.Filter | None:
    if not filters:
        return None

    must: list[Any] = []

    sites = _normalize_list(filters.get("site"))
    if sites:
        must.append(_filter_match_any("site", sites))
    base_urls = _normalize_list(filters.get("base_url"))
    if base_urls:
        must.append(_filter_match_any("base_url", base_urls))
    langs = _normalize_list(filters.get("lang"))
    if langs:
        must.append(_filter_match_any("lang", langs))
    authors = _normalize_list(filters.get("author"))
    if authors:
        must.append(_filter_match_any("author", authors))
    urls = _normalize_list(filters.get("url"))
    if urls:
        must.append(_filter_match_any("url", urls))

    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    if date_from or date_to:
        range_kwargs: dict[str, int] = {}
        if date_from:
            range_kwargs["gte"] = _parse_datetime(str(date_from))
        if date_to:
            range_kwargs["lte"] = _parse_datetime(str(date_to), end_of_day=True)
        range_conditions = []
        if range_kwargs:
            range_conditions.append(
                qmodels.FieldCondition(
                    key="published_at_ts",
                    range=qmodels.Range(**range_kwargs),
                )
            )
            range_conditions.append(
                qmodels.FieldCondition(
                    key="indexed_at_ts",
                    range=qmodels.Range(**range_kwargs),
                )
            )
        if range_conditions:
            must.append(qmodels.Filter(should=range_conditions))

    if not must:
        return None

    return qmodels.Filter(must=must)


def _recency_weight(
    payload: Mapping[str, Any],
    *,
    now_ts: int,
    half_life_hours: float,
) -> float:
    base_ts = payload.get("published_at_ts") or payload.get("indexed_at_ts")
    if not isinstance(base_ts, (int, float)):
        return 0.0
    delta_seconds = max(now_ts - int(base_ts), 0)
    if delta_seconds <= 0:
        return 1.0
    age_hours = delta_seconds / 3600
    if half_life_hours <= 0:
        return 1.0
    decay = math.exp(-math.log(2) * (age_hours / half_life_hours))
    return float(decay)


def _combine_scores(vector_score: float, recency_weight: float, *, recency_bias: float) -> float:
    # Clamp inputs to avoid negative or >1 values causing surprises.
    vs = max(vector_score, 0.0)
    rw = max(min(recency_weight, 1.2), 0.0)
    recency_bias = max(min(recency_bias, 0.9), 0.0)
    return (1.0 - recency_bias) * vs + recency_bias * rw


def _search_collection(
    client: QdrantClient,
    *,
    collection_name: str,
    query_vector: Sequence[float],
    limit: int,
    filters: Mapping[str, Any] | None,
    now: datetime | None,
    half_life_hours: float,
    recency_bias: float,
    fetch_multiplier: int,
) -> list[SearchResult]:
    search_filter = _build_filter(filters)
    fetch_limit = max(limit * fetch_multiplier, limit)

    search_params = qmodels.SearchParams(hnsw_ef=256)
    points = client.search(
        collection_name=collection_name,
        query_vector=list(query_vector),
        limit=fetch_limit,
        with_payload=True,
        with_vectors=False,
        search_params=search_params,
        query_filter=search_filter,
    )

    now_ts = _now_timestamp(now)
    results: list[SearchResult] = []
    for point in points:
        payload: dict[str, Any] = dict(point.payload or {})
        recency = _recency_weight(payload, now_ts=now_ts, half_life_hours=half_life_hours)
        combined = _combine_scores(point.score or 0.0, recency, recency_bias=recency_bias)
        results.append(
            SearchResult(
                id=str(point.id),
                payload=payload,
                vector_score=float(point.score or 0.0),
                recency_weight=recency,
                combined_score=combined,
            )
        )

    results.sort(
        key=lambda item: (
            -item.combined_score,
            -float(item.payload.get("published_at_ts") or item.payload.get("indexed_at_ts") or 0),
        )
    )
    return results[:limit]


def search_articles(
    client: QdrantClient,
    query_vector: Sequence[float],
    *,
    limit: int = 10,
    filters: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    half_life_hours: float = HALF_LIFE_HOURS,
    recency_bias: float = RECENCY_WEIGHT,
    fetch_multiplier: int = FETCH_MULTIPLIER,
    collection: str = ARTICLES_COLLECTION,
) -> list[SearchResult]:
    """Run a semantic article search with filters and recency-aware ranking."""

    return _search_collection(
        client,
        collection_name=collection,
        query_vector=query_vector,
        limit=limit,
        filters=filters,
        now=now,
        half_life_hours=half_life_hours,
        recency_bias=recency_bias,
        fetch_multiplier=fetch_multiplier,
    )


def search_chunks(
    client: QdrantClient,
    query_vector: Sequence[float],
    *,
    limit: int = 10,
    filters: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    half_life_hours: float = HALF_LIFE_HOURS,
    recency_bias: float = RECENCY_WEIGHT,
    fetch_multiplier: int = FETCH_MULTIPLIER,
    collection: str = CHUNKS_COLLECTION,
) -> list[SearchResult]:
    """Run a semantic chunk search with filters and recency-aware ranking."""

    return _search_collection(
        client,
        collection_name=collection,
        query_vector=query_vector,
        limit=limit,
        filters=filters,
        now=now,
        half_life_hours=half_life_hours,
        recency_bias=recency_bias,
        fetch_multiplier=fetch_multiplier,
    )


def _timestamp_from_payload(payload: Mapping[str, Any]) -> int:
    value = payload.get("published_at_ts") or payload.get("indexed_at_ts")
    try:
        return int(value)
    except (TypeError, ValueError):  # noqa: BLE001
        return 0


def _collect_sites(
    client: QdrantClient,
    *,
    base_filter: Mapping[str, Any] | None,
    collection: str,
    limit: int,
) -> list[str]:
    discovered: list[str] = []
    seen: set[str] = set()
    filter_without_site = dict(base_filter or {})
    filter_without_site.pop("site", None)
    query_filter = _build_filter(filter_without_site)

    offset = None
    while len(discovered) < limit:
        points, offset = client.scroll(
            collection_name=collection,
            scroll_filter=query_filter,
            with_payload=True,
            limit=128,
            offset=offset,
        )
        if not points:
            break
        for point in points:
            payload = point.payload or {}
            site = payload.get("site")
            if isinstance(site, str) and site not in seen:
                seen.add(site)
                discovered.append(site)
                if len(discovered) >= limit:
                    break
        if offset is None:
            break
    return discovered


def latest_by_site(
    client: QdrantClient,
    *,
    filters: Mapping[str, Any] | None = None,
    per_site: int = 5,
    now: datetime | None = None,
    collection: str = ARTICLES_COLLECTION,
    half_life_hours: float = HALF_LIFE_HOURS,
    site_limit: int = SITE_DISCOVERY_LIMIT,
) -> dict[str, list[SearchResult]]:
    """Fetch the most recent articles grouped per site."""

    base_filters = dict(filters or {})
    explicit_sites = _normalize_list(base_filters.get("site"))
    sites = explicit_sites or _collect_sites(
        client,
        base_filter=base_filters,
        collection=collection,
        limit=site_limit,
    )

    now_ts = _now_timestamp(now)
    results: dict[str, list[SearchResult]] = {}

    for site in sites:
        site_filters = dict(base_filters)
        site_filters["site"] = [site]
        filter_obj = _build_filter(site_filters)

        collected = []
        offset = None
        while len(collected) < per_site * 3:
            points, offset = client.scroll(
                collection_name=collection,
                scroll_filter=filter_obj,
                with_payload=True,
                limit=per_site * 3,
                offset=offset,
            )
            if not points:
                break
            collected.extend(points)
            if offset is None:
                break

        ranked = []
        for point in collected:
            payload = dict(point.payload or {})
            recency = _recency_weight(payload, now_ts=now_ts, half_life_hours=half_life_hours)
            combined = recency
            ranked.append(
                SearchResult(
                    id=str(point.id),
                    payload=payload,
                    vector_score=0.0,
                    recency_weight=recency,
                    combined_score=combined,
                )
            )

        ranked.sort(
            key=lambda item: (
                -_timestamp_from_payload(item.payload),
                -item.combined_score,
            )
        )
        if ranked:
            results[site] = ranked[:per_site]

    return results


__all__ = [
    "SearchResult",
    "search_articles",
    "search_chunks",
    "latest_by_site",
    "HALF_LIFE_HOURS",
    "RECENCY_WEIGHT",
]
