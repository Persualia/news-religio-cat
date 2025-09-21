"""Text chunking helpers for downstream embedding and storage."""
from __future__ import annotations

from typing import Iterable, List


def chunk_text(text: str, *, max_words: int = 800, overlap: int = 120) -> List[str]:
    """Split `text` into word-based windows with configurable overlap."""
    if not text:
        return []

    if max_words <= overlap:
        raise ValueError("max_words must be greater than overlap")

    words = text.split()
    if not words:
        return []

    step = max_words - overlap
    chunks: list[str] = []
    for start in range(0, len(words), step):
        window = words[start : start + max_words]
        if not window:
            break
        chunks.append(" ".join(window))
    return chunks


def chunk_articles(texts: Iterable[str], *, max_words: int = 800, overlap: int = 120) -> List[List[str]]:
    """Chunk an iterable of article contents, returning a list per article."""
    return [chunk_text(text, max_words=max_words, overlap=overlap) for text in texts]


__all__ = ["chunk_text", "chunk_articles"]
