"""Ensure Qdrant collections are created."""
from vector_client import get_client
from pipeline.qdrant_ops import (
    ARTICLES_COLLECTION,
    CHUNKS_COLLECTION,
    ensure_collections,
)


def main() -> None:
    client = get_client()
    ensure_collections(client)
    print(
        f"Ensured collections: {ARTICLES_COLLECTION}, {CHUNKS_COLLECTION}"
    )


if __name__ == "__main__":
    main()
