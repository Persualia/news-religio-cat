"""Slack notifier implementation using webhooks or bot token."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from config import SlackSettings, get_settings

logger = logging.getLogger(__name__)

DEFAULT_CHANNEL = "#catalunya-religio"
SLACK_CHAT_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"


class SlackNotifier:
    """Thin wrapper around Slack notifications."""

    def __init__(self) -> None:
        settings = get_settings().slack
        self._webhook_url: Optional[str] = settings.webhook_url
        self._bot_token: Optional[str] = settings.bot_token

    def notify(self, message: str) -> None:
        stripped = message.strip()
        if not stripped:
            logger.debug("Skipping Slack notification with empty message.")
            return

        if self._bot_token:
            self._send_via_api(stripped)
            return

        if self._webhook_url:
            self._send_via_webhook(stripped)
            return

        logger.debug("Slack credentials not configured; skipping notification: %s", stripped)

    def notify_blocks(self, *, blocks: list[dict], text: Optional[str] = None) -> None:
        if not blocks:
            logger.debug("Skipping Slack block notification with empty payload.")
            return

        if self._bot_token:
            payload = {
                "channel": DEFAULT_CHANNEL,
                "blocks": blocks,
                "link_names": True,
            }
            if text:
                payload["text"] = text
            self._post_via_api(payload)
            return

        if self._webhook_url:
            payload = {"blocks": blocks, "channel": DEFAULT_CHANNEL}
            if text:
                payload["text"] = text
            self._post_via_webhook(payload)
            return

        logger.debug("Slack credentials not configured; skipping block notification.")

    def _send_via_api(self, message: str) -> None:
        payload = {
            "channel": DEFAULT_CHANNEL,
            "text": message,
            "link_names": True,
        }
        self._post_via_api(payload)

    def _post_via_api(self, payload: dict) -> None:
        headers = {
            "Authorization": f"Bearer {self._bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        try:
            response = httpx.post(SLACK_CHAT_POST_MESSAGE_URL, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            if not data.get("ok", False):
                raise RuntimeError(f"Slack API error: {data}")
        except Exception as exc:  # noqa: BLE001 - we want to log any failure
            logger.warning("Failed to send Slack message via API: %s", exc)

    def _send_via_webhook(self, message: str) -> None:
        payload = {"text": message, "channel": DEFAULT_CHANNEL}
        self._post_via_webhook(payload)

    def _post_via_webhook(self, payload: dict) -> None:
        try:
            response = httpx.post(self._webhook_url, json=payload, timeout=10)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send Slack message via webhook: %s", exc)

__all__ = ["SlackNotifier"]
