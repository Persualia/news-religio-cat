"""Utility helpers for generating embeddings with OpenAI."""
from __future__ import annotations

from typing import Iterable, Sequence

from openai import OpenAI

from config import get_settings

_MODEL_NAME = "text-embedding-3-small"
_CLIENT: OpenAI | None = None


def _get_client() -> OpenAI:
    """Instantiate a singleton OpenAI client using cached settings."""
    global _CLIENT
    if _CLIENT is None:
        settings = get_settings()
        _CLIENT = OpenAI(api_key=settings.openai.api_key)
    return _CLIENT


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Embed a sequence of texts, returning one embedding per element."""
    if not texts:
        return []

    client = _get_client()
    response = client.embeddings.create(model=_MODEL_NAME, input=list(texts))
    return [record.embedding for record in response.data]


def embed_text(text: str) -> list[float]:
    """Embed a single text value and return its embedding vector."""
    return embed_texts([text])[0]


def embed_chunks(chunks: Iterable[str]) -> list[list[float]]:
    """Helper for embedding chunk generator output (materializes the iterable)."""
    return embed_texts(list(chunks))


__all__ = ["embed_texts", "embed_text", "embed_chunks"]
