"""Helpers for managing Qdrant collections and bulk operations."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Mapping
import hashlib
import uuid

from typing import TYPE_CHECKING

try:  # pragma: no cover - allow import to fail in tests without dependency
    from qdrant_client.http import exceptions as qexc
    from qdrant_client.http import models as qmodels
except ModuleNotFoundError:  # pragma: no cover - tests may skip installing qdrant-client
    qexc = None
    qmodels = None

from config import get_settings
from models import Article, Chunk

if TYPE_CHECKING:  # pragma: no cover
    from qdrant_client import QdrantClient
VECTOR_DIM = 1536
_SETTINGS = get_settings()
ARTICLES_COLLECTION = _SETTINGS.qdrant.articles_collection
CHUNKS_COLLECTION = _SETTINGS.qdrant.chunks_collection


def ensure_collections(client: "QdrantClient") -> None:
    """Ensure that the articles and chunks collections exist in Qdrant."""

    if qmodels is None:
        raise RuntimeError("qdrant-client is required to manage collections")

    desired = {
        ARTICLES_COLLECTION: qmodels.VectorParams(
            size=VECTOR_DIM,
            distance=qmodels.Distance.COSINE,
        ),
        CHUNKS_COLLECTION: qmodels.VectorParams(
            size=VECTOR_DIM,
            distance=qmodels.Distance.COSINE,
        ),
    }

    existing = set()
    try:
        response = client.get_collections()
        existing = {collection.name for collection in response.collections or []}
    except qexc.UnexpectedResponse:
        # If the API call fails we optimistically try to create the collections.
        existing = set()

    for name, vector_params in desired.items():
        if name not in existing:
            client.create_collection(
                collection_name=name,
                vectors_config=vector_params,
                optimizers_config=qmodels.OptimizersConfigDiff(indexing_threshold=20000),
                hnsw_config=qmodels.HnswConfigDiff(m=16, ef_construct=128),
                on_disk_payload=True,
            )

        for field, schema in {
            "site": qmodels.PayloadSchemaType.KEYWORD,
            "base_url": qmodels.PayloadSchemaType.KEYWORD,
            "lang": qmodels.PayloadSchemaType.KEYWORD,
            "author": qmodels.PayloadSchemaType.KEYWORD,
            "url": qmodels.PayloadSchemaType.KEYWORD,
            "article_id": qmodels.PayloadSchemaType.KEYWORD,
            "published_at_ts": qmodels.PayloadSchemaType.INTEGER,
            "indexed_at_ts": qmodels.PayloadSchemaType.INTEGER,
        }.items():
            try:
                client.create_payload_index(
                    collection_name=name,
                    field_name=field,
                    field_schema=schema,
                )
            except qexc.UnexpectedResponse as exc:  # pragma: no cover - already indexed
                if getattr(exc, "status_code", None) != 409:
                    raise


def _to_timestamp(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.astimezone(timezone.utc).timestamp())


def _hash_to_uuid(value: str) -> str:
    """Convert an arbitrary string into a stable UUID derived from its SHA1 hash."""

    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:32]
    return str(uuid.UUID(hex=digest))


def _article_payload(article: Article) -> dict:
    doc = article.to_document()
    payload = {
        **doc,
        "doc_id": article.doc_id,
        "base_url": article.base_url,
        "published_at_ts": _to_timestamp(article.published_at),
        "indexed_at_ts": _to_timestamp(article.indexed_at),
    }
    return payload


def index_articles(
    client: "QdrantClient",
    articles: Iterable[Article],
    article_vectors: Mapping[str, list[float]],
    *,
    collection: str | None = None,
) -> None:
    """Upsert article points into Qdrant.

    Articles without an accompanying embedding are skipped.
    """

    if qmodels is None:
        raise RuntimeError("qdrant-client is required to index articles")

    target = collection or ARTICLES_COLLECTION
    points: list[qmodels.PointStruct] = []

    for article in articles:
        vector = article_vectors.get(article.doc_id)
        if not vector:
            continue
        points.append(
            qmodels.PointStruct(
                id=_hash_to_uuid(article.doc_id),
                vector=vector,
                payload=_article_payload(article),
            )
        )

    if points:
        client.upsert(collection_name=target, points=points)


def _chunk_payload(chunk: Chunk) -> dict:
    article = chunk.article
    payload = {
        "doc_id": chunk.doc_id,
        "article_id": article.doc_id,
        "article_title": article.title,
        "article_description": article.description,
        "site": article.site,
        "url": article.url,
        "base_url": article.base_url,
        "lang": article.lang,
        "author": article.author,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "published_at_ts": _to_timestamp(article.published_at),
        "indexed_at": article.indexed_at.isoformat(),
        "indexed_at_ts": _to_timestamp(article.indexed_at),
        "chunk_ix": chunk.chunk_ix,
        "content": chunk.content,
    }
    return {key: value for key, value in payload.items() if value is not None}


def index_chunks(
    client: "QdrantClient",
    chunks: Iterable[Chunk],
    *,
    collection: str | None = None,
) -> None:
    """Upsert chunk points into Qdrant."""

    if qmodels is None:
        raise RuntimeError("qdrant-client is required to index chunks")

    target = collection or CHUNKS_COLLECTION
    points: list[qmodels.PointStruct] = []

    for chunk in chunks:
        points.append(
            qmodels.PointStruct(
                id=_hash_to_uuid(chunk.doc_id),
                vector=chunk.content_vec,
                payload=_chunk_payload(chunk),
            )
        )

    if points:
        client.upsert(collection_name=target, points=points)


def find_existing_article_ids(
    client: "QdrantClient",
    ids: Iterable[str],
    *,
    collection: str | None = None,
) -> set[str]:
    """Return the subset of ``ids`` that already exist in the articles collection."""

    id_list = [doc_id for doc_id in ids if doc_id]
    if not id_list:
        return set()

    if qmodels is None or qexc is None:
        raise RuntimeError("qdrant-client is required to query existing article ids")

    target = collection or ARTICLES_COLLECTION
    found: set[str] = set()

    batch_size = 256
    id_chunks: list[list[str]] = []
    hashed_to_original: dict[str, str] = {}
    for start in range(0, len(id_list), batch_size):
        batch = id_list[start : start + batch_size]
        hashed_batch = []
        for item in batch:
            hashed = _hash_to_uuid(item)
            hashed_batch.append(hashed)
            hashed_to_original[hashed] = item
        id_chunks.append(hashed_batch)

    for hashed_batch in id_chunks:
        try:
            points = client.retrieve(collection_name=target, ids=hashed_batch, with_payload=False)
        except qexc.UnexpectedResponse as exc:  # pragma: no cover - surfaced to caller
            if getattr(exc, "status_code", None) == 404:
                break
            raise
        for point in points:
            if point and point.id:
                original = hashed_to_original.get(str(point.id))
                if original:
                    found.add(original)

    return found


__all__ = [
    "ensure_collections",
    "index_articles",
    "index_chunks",
    "find_existing_article_ids",
    "ARTICLES_COLLECTION",
    "CHUNKS_COLLECTION",
]
