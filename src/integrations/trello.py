"""Trello client wrapper for creating news cards."""
from __future__ import annotations

import logging
from typing import Optional

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
        self._http = httpx.Client(timeout=self._timeout)
        self._label_cache: dict[str, str] = {}

    def create_card(self, item: NewsItem) -> str:
        """Create a Trello card for the provided news item."""

        payload: dict[str, object] = {
            "idList": self._settings.list_id,
            "name": item.title,
            #"desc": _build_description(item),
            "start": item.published_at.isoformat(),
            "pos": "top",
        }

        label_id = self._ensure_label(item.source)
        if label_id:
            payload["idLabels"] = [label_id]

        try:
            response = self._request("POST", "/cards", json=payload)
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to create Trello card for %s: %s", item.url, exc)
            raise

        card_id = data.get("id")
        if not card_id:
            logger.warning("Trello response missing card ID for %s", item.url)
            return ""

        self._attach_url(card_id, item.url)
        return card_id

    # -- Internal helpers -------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ) -> httpx.Response:
        params = params.copy() if params else {}
        params.update(
            {
                "key": self._settings.api_key,
                "token": self._settings.token,
            }
        )
        response = self._http.request(method, f"{TRELLO_API_BASE}{path}", params=params, json=json)
        response.raise_for_status()
        return response

    def _ensure_label(self, name: str | None) -> Optional[str]:
        if not name:
            return None
        if name in self._label_cache:
            return self._label_cache[name]

        # Refresh cache with existing labels
        try:
            response = self._request("GET", f"/boards/{self._settings.board_id}/labels", params={"limit": 1000})
            labels = response.json()
            for label in labels:
                label_name = (label.get("name") or "").strip()
                label_id = label.get("id")
                if label_name and label_id:
                    self._label_cache[label_name] = label_id
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch Trello labels: %s", exc)

        if name in self._label_cache:
            return self._label_cache[name]

        # Create label if it doesn't exist
        try:
            response = self._request(
                "POST",
                "/labels",
                json={
                    "name": name,
                    "idBoard": self._settings.board_id,
                    "color": None,
                },
            )
            created = response.json()
            label_id = created.get("id")
            if label_id:
                self._label_cache[name] = label_id
                return label_id
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to create Trello label '%s': %s", name, exc)
        return None

    def _attach_url(self, card_id: str, url: str) -> None:
        try:
            self._request("POST", f"/cards/{card_id}/attachments", params={"url": url})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to attach URL to card %s: %s", card_id, exc)


def _build_description(item: NewsItem) -> str:
    if item.summary:
        return item.summary.strip()
    return item.url


__all__ = ["TrelloClient"]
