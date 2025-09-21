"""Logging helpers for the ingestion pipeline."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional


DEFAULT_LOG_PATH = None
NOISY_LOGGERS = [
    "httpcore.http11",
    "httpcore.connection",
    "httpcore.connectionpool",
    "httpcore.proxy",
    "httpx",
]


def setup_logging(
    *,
    level: int = logging.INFO,
    log_path: Optional[Path] = None,
    fmt: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
) -> None:
    """Configure root logging with console and file handlers."""
    logger = logging.getLogger()
    logger.setLevel(level)

    # Avoid duplicating handlers if setup_logging is called multiple times.
    if not any(isinstance(handler, logging.StreamHandler) for handler in logger.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(stream_handler)

    noisy_level = logging.WARNING if level < logging.WARNING else level
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(noisy_level)


__all__ = ["setup_logging", "DEFAULT_LOG_PATH"]
