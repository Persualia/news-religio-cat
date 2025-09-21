"""Helpers for managing OpenSearch indices, templates, and bulk indexing."""
from __future__ import annotations

from datetime import datetime, timezone
import copy
from typing import Iterable

from opensearchpy import OpenSearch, helpers
from opensearchpy.exceptions import AuthorizationException

from models import Article, Chunk

ARTICLES_TEMPLATE_NAME = "articles-template"
CHUNKS_TEMPLATE_NAME = "chunks-template"
ARTICLES_ALIAS = "articles-live"
CHUNKS_ALIAS = "chunks-live"
VECTOR_DIM = 1536


ARTICLES_TEMPLATE = {
    "index_patterns": ["articles-*"] ,
    "template": {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 1,
            "refresh_interval": "1s",
            "analysis": {
                "analyzer": {
                    "es_std": {"type": "standard", "stopwords": "_spanish_"}
                }
            },
        },
        "mappings": {
            "properties": {
                "site": {"type": "keyword"},
                "url": {"type": "keyword"},
                "lang": {"type": "keyword"},
                "author": {"type": "keyword"},
                "published_at": {"type": "date"},
                "indexed_at": {"type": "date"},
                "title": {
                    "type": "text",
                    "analyzer": "es_std",
                    "copy_to": ["search_text_short", "search_text"],
                },
                "description": {
                    "type": "text",
                    "analyzer": "es_std",
                    "copy_to": ["search_text_short", "search_text"],
                },
                "content": {
                    "type": "text",
                    "analyzer": "es_std",
                    "copy_to": ["search_text"],
                },
                "search_text_short": {"type": "text", "analyzer": "es_std"},
                "search_text": {"type": "text", "analyzer": "es_std"},
            }
        },
    },
}


CHUNKS_TEMPLATE = {
    "index_patterns": ["chunks-*"] ,
    "template": {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 1,
            "refresh_interval": "1s",
            "knn": True,
            "analysis": {
                "analyzer": {
                    "es_std": {"type": "standard", "stopwords": "_spanish_"}
                }
            },
        },
        "mappings": {
            "properties": {
                "site": {"type": "keyword"},
                "url": {"type": "keyword"},
                "lang": {"type": "keyword"},
                "author": {"type": "keyword"},
                "published_at": {"type": "date"},
                "indexed_at": {"type": "date"},
                "chunk_ix": {"type": "integer"},
                "content": {"type": "text", "analyzer": "es_std"},
                "content_vec": {
                    "type": "knn_vector",
                    "dimension": VECTOR_DIM,
                    "method": {
                        "name": "hnsw",
                        "engine": "nmslib",
                        "space_type": "cosinesimil",
                    },
                },
            }
        },
    },
}


def _current_index(prefix: str, *, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{prefix}-{now.strftime('%Y.%m')}"


def ensure_templates(client: OpenSearch) -> bool:
    """Try to install composable templates; return False if forbidden."""

    try:
        client.indices.put_index_template(name=ARTICLES_TEMPLATE_NAME, body=ARTICLES_TEMPLATE)
        client.indices.put_index_template(name=CHUNKS_TEMPLATE_NAME, body=CHUNKS_TEMPLATE)
        return True
    except AuthorizationException as exc:
        # Some hosted providers (like Bonsai) restrict template APIs in lower tiers.
        if getattr(exc, "error", "") == "bonsai_exception":
            return False
        raise


def ensure_monthly_indices(
    client: OpenSearch,
    *,
    now: datetime | None = None,
    use_templates: bool = True,
) -> tuple[str, str]:
    articles_index = _current_index("articles", now=now)
    chunks_index = _current_index("chunks", now=now)

    index_payloads = {
        articles_index: copy.deepcopy(ARTICLES_TEMPLATE["template"]),
        chunks_index: copy.deepcopy(CHUNKS_TEMPLATE["template"]),
    }

    for index, alias in ((articles_index, ARTICLES_ALIAS), (chunks_index, CHUNKS_ALIAS)):
        if not client.indices.exists(index=index):
            body = None if use_templates else index_payloads[index]
            client.indices.create(index=index, body=body)
        _ensure_alias(client, alias=alias, target_index=index)

    return articles_index, chunks_index


def _ensure_alias(client: OpenSearch, *, alias: str, target_index: str) -> None:
    actions: list[dict] = []
    if client.indices.exists_alias(name=alias):
        existing = client.indices.get_alias(name=alias)
        for index_name in existing.keys():
            if index_name != target_index:
                actions.append({"remove": {"index": index_name, "alias": alias}})
    actions.append({"add": {"index": target_index, "alias": alias}})
    client.indices.update_aliases({"actions": actions})


def index_articles(client: OpenSearch, articles: Iterable[Article], *, index_name: str) -> None:
    actions = (
        {
            "_op_type": "index",
            "_index": index_name,
            "_id": article.doc_id,
            "_source": article.to_document(),
        }
        for article in articles
    )
    helpers.bulk(client, actions, stats_only=True)


def index_chunks(client: OpenSearch, chunks: Iterable[Chunk], *, index_name: str) -> None:
    actions = (
        {
            "_op_type": "index",
            "_index": index_name,
            "_id": chunk.doc_id,
            "_source": chunk.to_document(),
        }
        for chunk in chunks
    )
    helpers.bulk(client, actions, stats_only=True)


__all__ = [
    "ensure_templates",
    "ensure_monthly_indices",
    "index_articles",
    "index_chunks",
    "ARTICLES_ALIAS",
    "CHUNKS_ALIAS",
]
