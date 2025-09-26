"""Factory for a shared Qdrant client configured from environment settings."""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from config import get_settings

if TYPE_CHECKING:  # pragma: no cover
    from qdrant_client import QdrantClient


@lru_cache(maxsize=1)
def get_client():  # -> QdrantClient
    """Instantiate a shared Qdrant client using the configured credentials."""
    from qdrant_client import QdrantClient  # local import avoids hard dependency during module import
    settings = get_settings()
    qdrant_settings = settings.qdrant

    if not qdrant_settings.url:
        raise ValueError("QDRANT_URL must be configured")

    return QdrantClient(
        url=qdrant_settings.url,
        api_key=qdrant_settings.api_key,
        timeout=qdrant_settings.timeout,
        prefer_grpc=False,
    )


__all__ = ["get_client"]
