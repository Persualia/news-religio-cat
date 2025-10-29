"""Trello client wrapper for creating news cards."""
from __future__ import annotations

import logging
import httpx

from config import TrelloSettings, get_settings
from models import NewsItem

TRELLO_API_BASE = "https://api.trello.com/1"

logger = logging.getLogger(__name__)


class TrelloClient:
    """Simple wrapper around the Trello REST API."""

    def __init__(self, settings: TrelloSettings | None = None) -> None:
        self._settings = settings or get_settings().trello
        self._timeout = httpx.Timeout(10.0, connect=5.0)

    def create_card(self, item: NewsItem) -> str:
        """Create a Trello card for the provided news item.

        Returns:
            The Trello card identifier.
        """

        payload = {
            "idList": self._settings.list_id,
            "name": item.title,
            "desc": _build_description(item),
            "urlSource": item.url,
            "pos": "top",
        }
        params = {
            "key": self._settings.api_key,
            "token": self._settings.token,
        }
        try:
            response = httpx.post(
                f"{TRELLO_API_BASE}/cards",
                params=params,
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to create Trello card for %s: %s", item.url, exc)
            raise

        card_id = response.json().get("id")
        if not card_id:
            logger.warning("Trello response missing card ID for %s", item.url)
            return ""
        return card_id


def _build_description(item: NewsItem) -> str:
    if item.summary:
        return item.summary.strip()
    return item.url


__all__ = ["TrelloClient"]
