#!/usr/bin/env python3
"""Simulate the n8n search tool locally against Qdrant."""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from dotenv import load_dotenv

# Ensure project root on path before importing project modules
ROOT = Path(__file__).resolve().parents[2]
for candidate in (ROOT, ROOT / "src"):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from src.vector_client import get_client  # noqa: E402
from src.search.qdrant_search import (  # noqa: E402
    SearchResult,
    latest_by_site,
    search_articles,
    search_chunks,
)

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
    requires_embedding: bool

    @property
    def intent(self) -> str:
        return str(self.plan.get("intent"))


QUERIES_PATH = ROOT / "scripts" / "n8n" / "query_samples.yml"
INTENT_SAMPLES_PATH = ROOT / "scripts" / "n8n" / "intents_samples.json"
OUTPUT_DIR = ROOT / "scripts" / "n8n" / "results"

RECENCY_INFO_FIELDS = ["published_at", "indexed_at", "published_at_ts", "indexed_at_ts"]


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
    "site": "site",
    "author": "author",
    "lang": "lang",
    "base_url": "base_url",
    "url": "url",
}


def normalize_field_list(value: Any, fallback: Optional[List[str]] = None) -> List[str]:
    if isinstance(value, list) and value:
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return list(fallback) if fallback else []


def prepare_plan(raw: Dict[str, Any]) -> PreparedPlan:
    plan = json.loads(json.dumps(raw or {}))  # deep copy & ensure dict

    plan_top_k = clamp_int(plan.get("topK"), 1, 50, 5)
    plan["topK"] = plan_top_k

    intent = to_string_safe(plan.get("intent")) or "search_articles"
    plan["intent"] = intent

    if to_string_safe(plan.get("phrase")):
        query_text = strip_quotes(to_string_safe(plan["phrase"]))
    elif to_string_safe(plan.get("keywords")):
        query_text = to_string_safe(plan["keywords"])
    else:
        query_text = "notícies rellevants"

    plan_return = plan.get("return") or {}
    if not plan_return.get("index"):
        plan_return["index"] = "chunks" if intent == "search_chunks" else "articles"

    fields = normalize_field_list(plan_return.get("fields"))
    if not fields:
        if plan_return["index"] == "chunks":
            fields = [
                "url",
                "content",
                "chunk_ix",
                "published_at",
                "site",
                "lang",
                "author",
            ]
        else:
            fields = [
                "title",
                "url",
                "published_at",
                "site",
                "author",
                "description",
            ]
    plan_return["fields"] = fields
    plan["return"] = plan_return

    filters = plan.get("filters") or {}
    normalized_filters: Dict[str, Any] = {}
    for key, value in filters.items():
        if key in EXACT_FIELDS:
            values = normalize_field_list(value)
            if values:
                normalized_filters[key] = values
        else:
            normalized_filters[key] = value
    plan["filters"] = normalized_filters

    requires_embedding = intent in {"search_articles", "search_chunks"}

    return PreparedPlan(
        plan=plan,
        query_text=query_text,
        fields=fields,
        top_k=plan_top_k,
        requires_embedding=requires_embedding,
    )


def normalize_payload_fields(payload: Dict[str, Any], desired_fields: Sequence[str]) -> Dict[str, Any]:
    if not desired_fields:
        return dict(payload)
    extracted = {field: payload.get(field) for field in desired_fields}
    for field in RECENCY_INFO_FIELDS:
        if field not in extracted and field in payload:
            extracted[field] = payload[field]
    return extracted


def serialize_result(result: SearchResult, fields: Sequence[str]) -> Dict[str, Any]:
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


def maybe_get_embedding(client: OpenAI, text: str) -> List[float]:
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


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


def run_plan(
    client: Any,
    prepared: PreparedPlan,
    *,
    embedding: Optional[List[float]],
    now: datetime,
) -> Dict[str, Any]:
    intent = prepared.intent
    filters = prepared.plan.get("filters") or {}

    if intent == "latest_by_site":
        grouped = latest_by_site(
            client,
            filters=filters,
            per_site=prepared.top_k,
            now=now,
        )
        return {
            "intent": intent,
            "groups": {
                site: [serialize_result(result, prepared.fields) for result in results]
                for site, results in grouped.items()
            },
        }

    if intent == "search_articles":
        if embedding is None:
            raise ValueError("Embedding required for article search")
        hits = search_articles(
            client,
            embedding,
            limit=prepared.top_k,
            filters=filters,
            now=now,
        )
        return {
            "intent": intent,
            "hits": [serialize_result(result, prepared.fields) for result in hits],
        }

    if intent == "search_chunks":
        if embedding is None:
            raise ValueError("Embedding required for chunk search")
        hits = search_chunks(
            client,
            embedding,
            limit=prepared.top_k,
            filters=filters,
            now=now,
        )
        return {
            "intent": intent,
            "hits": [serialize_result(result, prepared.fields) for result in hits],
        }

    if intent == "summarize":
        return {"intent": intent, "hits": []}

    raise ValueError(f"Unsupported intent: {intent}")


def slugify(text: str) -> str:
    normalized = (
        re.sub(r"\s+", " ", text.strip().lower())
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or "query"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    queries = load_queries()
    intent_samples = load_intent_samples()

    openai_client = OpenAI()
    qdrant_client = get_client()

    summary_rows: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for idx, query in enumerate(queries, start=1):
        print(f"[{idx}/{len(queries)}] Procesant consulta: {query}")

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

        try:
            prepared = prepare_plan(plan_raw)
        except Exception as error:  # noqa: BLE001
            print(f"  ✖ Plan preparation error: {error}")
            record = {
                "query": query,
                "plan": plan_raw,
                "error": f"prepare_failed: {error}",
            }
            output_path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
            summary_rows.append(record)
            continue

        embedding: Optional[List[float]] = None
        if prepared.requires_embedding:
            try:
                embedding = maybe_get_embedding(openai_client, prepared.query_text)
            except Exception as error:  # noqa: BLE001
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
            search_output = run_plan(
                qdrant_client,
                prepared,
                embedding=embedding,
                now=now,
            )
        except Exception as error:  # noqa: BLE001
            print(f"  ✖ Search error: {error}")
            record = {
                "query": query,
                "plan": plan_raw,
                "prepared": prepared.__dict__,
                "error": f"search_failed: {error}",
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
                "requires_embedding": prepared.requires_embedding,
            },
            "search": search_output,
        }

        output_path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
        summary_rows.append(
            {
                "query": query,
                "intent": prepared.intent,
                "result_file": str(output_path.relative_to(ROOT)),
                "hit_count": len(search_output.get("hits", []))
                if "hits" in search_output
                else sum(len(v) for v in search_output.get("groups", {}).values()),
            }
        )
        print(f"  ✓ Guardado en {output_path}")

    summary_path = OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary_rows, indent=2, ensure_ascii=False))
    print(f"Resumen guardado en {summary_path}")


if __name__ == "__main__":
    main()
