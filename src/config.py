"""Centralized configuration loading for the ingestion pipeline."""
from __future__ import annotations

from dataclasses import dataclass
import os
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    """Retrieve a required environment variable or raise an explicit error."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _optional_env(name: str) -> Optional[str]:
    """Retrieve an optional environment variable, returning None if unset."""
    value = os.getenv(name)
    return value or None


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str


@dataclass(frozen=True)
class SummarySettings:
    endpoint: str
    auth_token: Optional[str]


@dataclass(frozen=True)
class ScraperSettings:
    user_agent: str
    request_timeout: float
    max_retries: int
    throttle_seconds: float


@dataclass(frozen=True)
class QdrantSettings:
    url: str
    api_key: Optional[str]
    articles_collection: str
    chunks_collection: str
    timeout: Optional[float]


@dataclass(frozen=True)
class Settings:
    openai: OpenAISettings
    summary: SummarySettings
    scraper: ScraperSettings
    qdrant: QdrantSettings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings from environment variables (cached)."""
    scraper_user_agent = (
        _optional_env("SCRAPER_USER_AGENT")
        or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    )

    return Settings(
        openai=OpenAISettings(api_key=_require_env("OPENAI_API_KEY")),
        summary=SummarySettings(
            endpoint=_require_env("N8N_SUMMARY_ENDPOINT"),
            auth_token=_optional_env("N8N_SUMMARY_AUTH_TOKEN"),
        ),
        scraper=ScraperSettings(
            user_agent=scraper_user_agent,
            request_timeout=float(_optional_env("SCRAPER_REQUEST_TIMEOUT") or 20),
            max_retries=int(_optional_env("SCRAPER_MAX_RETRIES") or 3),
            throttle_seconds=float(_optional_env("SCRAPER_THROTTLE_SECONDS") or 1.5),
        ),
        qdrant=QdrantSettings(
            url=_require_env("QDRANT_URL"),
            api_key=_optional_env("QDRANT_API_KEY"),
            articles_collection=_optional_env("QDRANT_COLLECTION_ARTICLES")
            or (_optional_env("QDRANT_COLLECTION_PREFIX") or "") + "articles",
            chunks_collection=_optional_env("QDRANT_COLLECTION_CHUNKS")
            or (_optional_env("QDRANT_COLLECTION_PREFIX") or "") + "chunks",
            timeout=float(_optional_env("QDRANT_TIMEOUT") or 30),
        ),
    )


__all__ = [
    "OpenAISettings",
    "SummarySettings",
    "ScraperSettings",
    "QdrantSettings",
    "Settings",
    "get_settings",
]
