#!/usr/bin/env python3
"""Simulate the n8n search tool locally and run all sample queries."""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from dotenv import load_dotenv

# Ensure project root on path before importing project modules
ROOT = Path(__file__).resolve().parents[2]
for candidate in (ROOT, ROOT / "src"):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from src.opensearch_client import get_client  # noqa: E402
from src.config import get_settings  # noqa: E402

try:
    from openai import OpenAI
except ImportError as exc:  # pragma: no cover - surface helpful error
    raise SystemExit("The 'openai' package is required. Install with pip install -r requirements.txt") from exc


load_dotenv()


@dataclass
class PreparedPlan:
    plan: Dict[str, Any]
    query_text: str
    fields: List[str]
    top_k: int
    semantic: bool
    mode: str


@dataclass
class DSLResult:
    url: str
    body: Dict[str, Any]
    intent: str
    target: str
    index_name: str


QUERIES_PATH = ROOT / "scripts" / "n8n" / "query_samples.yml"
INTENT_SAMPLES_PATH = ROOT / "scripts" / "n8n" / "intents_samples.json"
OUTPUT_DIR = ROOT / "scripts" / "n8n" / "results"


# ---------- Utilities mirroring the JS helpers ----------

def clamp_int(n: Optional[int], min_value: int, max_value: int, default: int) -> int:
    if n is None or not isinstance(n, int):
        return default
    return max(min_value, min(max_value, n))


def to_string_safe(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


QUOTE_PATTERN = re.compile(r"[“”«»\"']")


def strip_quotes(text: str) -> str:
    return QUOTE_PATTERN.sub("", text or "").strip()


EXACT_FIELDS = {
    "site": "site.keyword",
    "author": "author.keyword",
    "lang": "lang.keyword",
}


def resolve_field(field: str) -> str:
    return EXACT_FIELDS.get(field, field)


# ---------- Prepare plan (port from prepare_plan.js) ----------

def prepare_plan(raw: Dict[str, Any]) -> PreparedPlan:
    plan = json.loads(json.dumps(raw or {}))  # deep copy & ensure dict

    plan_top_k = clamp_int(plan.get("topK"), 1, 50, 5)
    plan["topK"] = plan_top_k

    mode = plan.get("mode")
    semantic_flag = bool(plan.get("semantic"))
    if not mode:
        mode = "hybrid" if semantic_flag else "lexical"
    plan["mode"] = mode
    plan["semantic"] = mode == "hybrid"

    if to_string_safe(plan.get("phrase")):
        query_text = strip_quotes(to_string_safe(plan["phrase"]))
    elif to_string_safe(plan.get("keywords")):
        query_text = to_string_safe(plan["keywords"])
    else:
        query_text = "notícies rellevants"

    plan_return = plan.get("return") or {}
    if not plan_return.get("index"):
        plan_return["index"] = "chunks" if plan.get("intent") == "search_chunks" else "articles"

    fields = plan_return.get("fields")
    if not isinstance(fields, list) or not fields:
        if plan_return["index"] == "chunks":
            plan_return["fields"] = [
                "url",
                "content",
                "chunk_ix",
                "published_at",
                "site",
                "lang",
                "author",
            ]
        else:
            plan_return["fields"] = [
                "title",
                "url",
                "published_at",
                "site",
                "author",
                "description",
            ]
    plan["return"] = plan_return
    fields = plan_return["fields"]

    filters = plan.get("filters") or {}
    for key in ("site", "lang", "author"):
        value = filters.get(key)
        if isinstance(value, list) and not value:
            filters.pop(key, None)
    plan["filters"] = filters

    plan_sort = plan.get("sort") or {"by": "published_at", "order": "desc"}
    plan["sort"] = plan_sort

    semantic = bool(plan.get("semantic"))

    return PreparedPlan(
        plan=plan,
        query_text=query_text,
        fields=fields,
        top_k=plan_top_k,
        semantic=semantic,
        mode=mode,
    )


# ---------- Build DSL (port from build_dsl.js) ----------

def term_filter(field: str, values: Optional[List[str]]) -> Optional[Dict[str, Any]]:
    if isinstance(values, list) and values:
        return {"terms": {resolve_field(field): values}}
    return None


def range_filter(field: str, gte: Optional[str], lte: Optional[str]) -> Optional[Dict[str, Any]]:
    range_body: Dict[str, str] = {}
    if gte:
        range_body["gte"] = gte
    if lte:
        range_body["lte"] = lte
    if range_body:
        return {"range": {field: range_body}}
    return None


def make_filters(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    must: List[Dict[str, Any]] = []
    if not filters:
        return must
    for clause in (
        term_filter("site", filters.get("site")),
        term_filter("lang", filters.get("lang")),
        term_filter("author", filters.get("author")),
        range_filter("published_at", filters.get("date_from"), filters.get("date_to")),
    ):
        if clause:
            must.append(clause)
    return must


def lexical_query_articles(plan: Dict[str, Any], query_text: str, must_filters: List[Dict[str, Any]]) -> Dict[str, Any]:
    should: List[Dict[str, Any]] = []
    if plan.get("phrase"):
        should.append({"match_phrase": {"title": query_text}})
        should.append({"match_phrase": {"description": query_text}})
    if plan.get("keywords") or (not plan.get("phrase") and query_text):
        should.append(
            {
                "multi_match": {
                    "query": query_text,
                    "fields": ["search_text_short^3", "title^4", "description^2", "content"],
                    "type": "best_fields",
                    "operator": "and",
                }
            }
        )
    return {
        "bool": {
            "must": must_filters,
            "should": should,
            "minimum_should_match": 1 if should else 0,
        }
    }


def lexical_query_chunks(plan: Dict[str, Any], query_text: str, must_filters: List[Dict[str, Any]]) -> Dict[str, Any]:
    should: List[Dict[str, Any]] = []
    if plan.get("phrase"):
        should.append({"match_phrase": {"content": query_text}})
    if plan.get("keywords") or (not plan.get("phrase") and query_text):
        should.append(
            {
                "multi_match": {
                    "query": query_text,
                    "fields": ["content"],
                    "type": "best_fields",
                    "operator": "and",
                }
            }
        )
    return {
        "bool": {
            "must": must_filters,
            "should": should,
            "minimum_should_match": 1 if should else 0,
        }
    }


def join_url(base: str, path: str) -> str:
    trimmed_base = base.rstrip("/") if base else ""
    trimmed_path = path.lstrip("/")
    return f"{trimmed_base}/{trimmed_path}" if trimmed_base else f"/{trimmed_path}"


def build_dsl(
    prepared: PreparedPlan,
    query_text: str,
    embedding: Optional[List[float]],
    base_url: str,
    index_articles: str,
    index_chunks: str,
) -> DSLResult:
    plan = prepared.plan
    filters_bool = make_filters(plan.get("filters") or {})
    sort_by = plan.get("sort", {}).get("by", "published_at")
    sort_order = plan.get("sort", {}).get("order", "desc")

    url = ""
    body: Dict[str, Any]
    target = "articles" if plan.get("return", {}).get("index") != "chunks" else "chunks"
    index_name = index_articles

    if plan["intent"] == "latest_by_site":
        top_hits: Dict[str, Any] = {
            "size": plan.get("topK", prepared.top_k),
            "sort": [{sort_by: {"order": sort_order, "unmapped_type": "date"}}],
        }
        if prepared.fields:
            top_hits["_source"] = prepared.fields
        body = {
            "size": 0,
            "query": {"bool": {"must": filters_bool}},
            "aggs": {
                "by_site": {
                    "terms": {"field": resolve_field("site"), "size": 50},
                    "aggs": {"latest": {"top_hits": top_hits}},
                }
            },
        }
        url = join_url(base_url, f"{index_articles}/_search")
        target = "aggs"
        index_name = index_articles
    elif plan["intent"] == "search_articles":
        if prepared.mode == "lexical":
            body = {
                "size": prepared.top_k,
                "query": lexical_query_articles(plan, query_text, filters_bool),
                "sort": [{sort_by: {"order": sort_order, "unmapped_type": "date"}}],
            }
            if prepared.fields:
                body["_source"] = prepared.fields
            url = join_url(base_url, f"{index_articles}/_search")
            target = "articles_lexical"
            index_name = index_articles
        else:
            if not embedding:
                raise ValueError("Missing embedding for hybrid article search")
            k = max(5 * prepared.top_k, 200)
            num_candidates = max(10 * prepared.top_k, 500)
            body = {
                "size": k,
                "_source": ["url", "site", "author", "published_at", "chunk_ix"],
                "query": {
                    "knn": {
                        "field": "content_vec",
                        "query_vector": embedding,
                        "k": k,
                        "num_candidates": num_candidates,
                        "filter": {"bool": {"must": filters_bool}},
                    }
                },
                "sort": [{sort_by: {"order": sort_order, "unmapped_type": "date"}}],
            }
            url = join_url(base_url, f"{index_chunks}/_search")
            target = "articles_from_chunks"
            index_name = index_chunks
    elif plan["intent"] == "search_chunks":
        if prepared.mode == "lexical":
            body = {
                "size": prepared.top_k,
                "query": lexical_query_chunks(plan, query_text, filters_bool),
                "sort": [{sort_by: {"order": sort_order, "unmapped_type": "date"}}],
            }
            if prepared.fields:
                body["_source"] = prepared.fields
            url = join_url(base_url, f"{index_chunks}/_search")
            target = "chunks_lexical"
            index_name = index_chunks
        else:
            if not embedding:
                raise ValueError("Missing embedding for hybrid chunk search")
            k = max(5 * prepared.top_k, 200)
            num_candidates = max(10 * prepared.top_k, 500)
            body = {
                "size": prepared.top_k,
                "_source": prepared.fields
                or ["url", "content", "chunk_ix", "published_at", "site", "lang", "author"],
                "query": {
                    "knn": {
                        "field": "content_vec",
                        "query_vector": embedding,
                        "k": k,
                        "num_candidates": num_candidates,
                        "filter": {"bool": {"must": filters_bool}},
                    }
                },
                "sort": [{sort_by: {"order": sort_order, "unmapped_type": "date"}}],
            }
            url = join_url(base_url, f"{index_chunks}/_search")
            target = "chunks_knn"
            index_name = index_chunks
    elif plan["intent"] == "summarize":
        body = {"size": 0, "query": {"match_none": {}}}
        url = join_url(base_url, f"{index_articles}/_search")
        target = "noop"
        index_name = index_articles
    else:
        raise ValueError(f"Unsupported intent: {plan['intent']}")

    return DSLResult(url=url, body=body, intent=plan["intent"], target=target, index_name=index_name)


# ---------- Orchestration helpers ----------

def load_intent_samples() -> Dict[str, Dict[str, Any]]:
    raw = json.loads(INTENT_SAMPLES_PATH.read_text())
    if not isinstance(raw, dict):
        raise ValueError("intents_samples.json must contain an object")

    samples: Dict[str, Dict[str, Any]] = {}
    for query, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        plan = payload.get("output", payload)
        if isinstance(plan, dict):
            samples[str(query)] = plan
    if not samples:
        raise ValueError("No usable plans found in intents_samples.json")
    return samples


def load_queries() -> List[str]:
    queries: List[str] = []
    for line in QUERIES_PATH.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            item = stripped[2:]
            if item.startswith("\"") and item.endswith("\"") and len(item) >= 2:
                item = item[1:-1]
            queries.append(item)
    if not queries:
        raise ValueError("No queries found in query_samples.yml")
    return queries


def slugify(text: str) -> str:
    normalized = (
        re.sub(r"\s+", " ", text.strip().lower())
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or "query"


def get_base_url(bonsai_url: str) -> Tuple[str, Tuple[str, str]]:
    parsed = urlparse(bonsai_url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError("Invalid BONSAI_URL; expected scheme and host")
    base = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        base = f"{base}:{parsed.port}"
    if not parsed.username or not parsed.password:
        raise ValueError("BONSAI_URL must embed credentials (username:password)")
    auth = (parsed.username, parsed.password)
    return base, auth


def maybe_get_embedding(client: OpenAI, text: str) -> List[float]:
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


def execute_search(dsl: DSLResult) -> Dict[str, Any]:
    client = get_client()
    response = client.search(index=dsl.index_name, body=dsl.body)
    return response


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    settings = get_settings()
    base_url, _auth = get_base_url(settings.bonsai.url)
    queries = load_queries()
    intent_samples = load_intent_samples()

    openai_client = OpenAI()

    summary_rows: List[Dict[str, Any]] = []

    for idx, query in enumerate(queries, start=1):
        print(f"[{idx}/{len(queries)}] Procesando consulta: {query}")

        file_slug = f"{idx:02d}_{slugify(query)[:60]}"
        output_path = OUTPUT_DIR / f"{file_slug}.json"

        plan_raw = intent_samples.get(query)
        if not plan_raw:
            print("  ✖ Plan not found in intents_samples.json")
            record = {
                "query": query,
                "error": "plan_missing",
            }
            output_path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
            summary_rows.append(record)
            continue

        prepared = prepare_plan(plan_raw)
        embedding: Optional[List[float]] = None
        if prepared.semantic:
            try:
                embedding = maybe_get_embedding(openai_client, prepared.query_text)
            except Exception as error:
                print(f"  ✖ Embedding error: {error}")
                record = {
                    "query": query,
                    "plan": plan_raw,
                    "prepared": prepared.__dict__,
                    "error": f"embedding_failed: {error}",
                }
                output_path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
                summary_rows.append(record)
                continue

        try:
            dsl = build_dsl(
                prepared=prepared,
                query_text=prepared.query_text,
                embedding=embedding,
                base_url=base_url,
                index_articles="articles-live",
                index_chunks="chunks-live",
            )
        except Exception as error:
            print(f"  ✖ DSL error: {error}")
            record = {
                "query": query,
                "plan": plan_raw,
                "prepared": prepared.__dict__,
                "error": f"dsl_failed: {error}",
            }
            output_path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
            summary_rows.append(record)
            continue

        fallback_used = False
        try:
            search_response = execute_search(dsl)
        except Exception as error:
            error_message = str(error)
            if prepared.semantic and "unknown query [knn]" in error_message:
                print("  ↻ kNN no disponible; reintentando en modo lexical")
                fallback_plan_raw = json.loads(json.dumps(prepared.plan))
                fallback_plan_raw["mode"] = "lexical"
                fallback_plan_raw["semantic"] = False
                fallback_prepared = prepare_plan(fallback_plan_raw)
                try:
                    fallback_dsl = build_dsl(
                        prepared=fallback_prepared,
                        query_text=fallback_prepared.query_text,
                        embedding=None,
                        base_url=base_url,
                        index_articles="articles-live",
                        index_chunks="chunks-live",
                    )
                    search_response = execute_search(fallback_dsl)
                    prepared = fallback_prepared
                    dsl = fallback_dsl
                    fallback_used = True
                except Exception as fallback_error:
                    error = fallback_error
                    error_message = str(fallback_error)
            if not fallback_used:
                print(f"  ✖ OpenSearch error: {error_message}")
                record = {
                    "query": query,
                    "plan": plan_raw,
                    "prepared": prepared.__dict__,
                    "dsl": dsl.__dict__,
                    "error": f"opensearch_failed: {error_message}",
                }
                output_path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
                summary_rows.append(record)
                continue

        record = {
            "query": query,
            "plan": plan_raw,
            "prepared": {
                "plan": prepared.plan,
                "query_text": prepared.query_text,
                "fields": prepared.fields,
                "top_k": prepared.top_k,
                "semantic": prepared.semantic,
                "mode": prepared.mode,
            },
            "dsl": {
                "url": dsl.url,
                "body": dsl.body,
                "intent": dsl.intent,
                "target": dsl.target,
                "index_name": dsl.index_name,
            },
            "opensearch_response": search_response,
        }
        if fallback_used:
            record["fallback"] = "semantic_disabled_due_to_missing_knn"

        output_path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
        summary_rows.append(
            {
                "query": query,
                "intent": dsl.intent,
                "target": dsl.target,
                "hits": search_response.get("hits", {}).get("total"),
                "output_file": str(output_path.relative_to(ROOT)),
                "fallback": fallback_used,
            }
        )
        print(f"  ✓ Guardado en {output_path}")

    summary_path = OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary_rows, indent=2, ensure_ascii=False))
    print(f"Resumen guardado en {summary_path}")


if __name__ == "__main__":
    main()
