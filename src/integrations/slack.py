"""Slack notifier implementation using webhooks or bot token."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from config import SlackSettings, get_settings

logger = logging.getLogger(__name__)

DEFAULT_TARGET = "@albert"
SLACK_CHAT_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"


class SlackNotifier:
    """Thin wrapper around Slack notifications."""

    def __init__(self) -> None:
        settings = get_settings().slack
        self._webhook_url: Optional[str] = settings.webhook_url
        self._bot_token: Optional[str] = settings.bot_token
        self._target_user: str = settings.target_user or DEFAULT_TARGET

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

    def _send_via_api(self, message: str) -> None:
        channel = self._normalize_target(self._target_user)
        payload = {"channel": channel, "text": message, "link_names": True}
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
        formatted = self._ensure_mention(message)
        try:
            response = httpx.post(self._webhook_url, json={"text": formatted}, timeout=10)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send Slack message via webhook: %s", exc)

    @staticmethod
    def _normalize_target(target: str) -> str:
        stripped = target.strip()
        if not stripped:
            return DEFAULT_TARGET
        if not stripped.startswith("@") and not stripped.startswith("#"):
            return f"@{stripped}"
        return stripped

    @staticmethod
    def _ensure_mention(message: str) -> str:
        mention = f"<{DEFAULT_TARGET}>"
        stripped = message.strip()
        if stripped.startswith(mention):
            return stripped
        return f"{mention} {stripped}"


__all__ = ["SlackNotifier"]
