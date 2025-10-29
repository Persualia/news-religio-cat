"""Slack webhook notifier."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from config import SlackSettings, get_settings

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Thin wrapper around an incoming Slack webhook."""

    def __init__(self, settings: SlackSettings | None = None) -> None:
        if settings is None:
            settings = get_settings().slack
        self._webhook_url: Optional[str] = settings.webhook_url

    def notify(self, message: str) -> None:
        if not self._webhook_url:
            logger.debug("Slack webhook not configured; skipping notification: %s", message)
            return
        try:
            response = httpx.post(self._webhook_url, json={"text": message}, timeout=10)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - we want to log any failure
            logger.warning("Failed to send Slack notification: %s", exc)


__all__ = ["SlackNotifier"]
