"""Utility script to send a test notification to Slack."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure src is on the path.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from integrations import SlackNotifier
from logging_utils import setup_logging

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a test Slack notification using pipeline settings")
    parser.add_argument(
        "--message",
        help="Custom message to send. If omitted, a default test message with timestamp is used.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    level = getattr(logging, args.log_level.upper())
    setup_logging(level=level)

    notifier = SlackNotifier()
    timestamp = datetime.now(timezone.utc).isoformat()
    message = args.message or f":information_source: Slack test notification at {timestamp}"

    logger.info("Sending Slack test notification at %s", timestamp)
    notifier.notify(message)
    logger.info("Slack test notification dispatched.")


if __name__ == "__main__":
    main()
