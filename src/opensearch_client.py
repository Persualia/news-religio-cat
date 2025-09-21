"""OpenSearch client factory configured for Bonsai.io."""
from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from opensearchpy import OpenSearch

from config import get_settings


@lru_cache(maxsize=1)
def get_client() -> OpenSearch:
    """Instantiate a shared OpenSearch client using Bonsai credentials."""
    settings = get_settings()
    parsed = urlparse(settings.bonsai.url)

    if not parsed.hostname or not parsed.username or not parsed.password:
        raise ValueError("Invalid BONSAI_URL; must include credentials and host")

    return OpenSearch(
        hosts=[{"host": parsed.hostname, "port": parsed.port or 443}],
        http_auth=(parsed.username, parsed.password),
        use_ssl=True,
        verify_certs=True,
        scheme=parsed.scheme or "https",
    )


__all__ = ["get_client"]
