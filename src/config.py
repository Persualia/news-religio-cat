"""Centralised configuration loading for the Trello ingestion pipeline."""
from __future__ import annotations

from dataclasses import dataclass
import os
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _optional_env(name: str) -> Optional[str]:
    value = os.getenv(name)
    return value or None


@dataclass(frozen=True)
class ScraperSettings:
    user_agent: str
    request_timeout: float
    max_retries: int
    throttle_seconds: float


@dataclass(frozen=True)
class TrelloSettings:
    api_key: str
    token: str
    board_id: str
    list_id: str


@dataclass(frozen=True)
class SlackSettings:
    webhook_url: Optional[str]
    bot_token: Optional[str]
    target_user: Optional[str]


@dataclass(frozen=True)
class GoogleSettings:
    project_id: str
    client_email: str
    private_key: str
    sheet_id: str
    worksheet: Optional[str]
    private_key_id: Optional[str]
    client_id: Optional[str]
    token_uri: str
    auth_uri: str
    auth_provider_x509_cert_url: Optional[str]
    client_x509_cert_url: Optional[str]
    universe_domain: Optional[str]


@dataclass(frozen=True)
class Settings:
    scraper: ScraperSettings
    trello: TrelloSettings
    slack: SlackSettings
    google: GoogleSettings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    scraper_user_agent = (
        _optional_env("SCRAPER_USER_AGENT")
        or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    )

    google_private_key = _require_env("GOOGLE_PRIVATE_KEY").replace("\\n", "\n")

    return Settings(
        scraper=ScraperSettings(
            user_agent=scraper_user_agent,
            request_timeout=float(_optional_env("SCRAPER_REQUEST_TIMEOUT") or 20),
            max_retries=int(_optional_env("SCRAPER_MAX_RETRIES") or 3),
            throttle_seconds=float(_optional_env("SCRAPER_THROTTLE_SECONDS") or 1.5),
        ),
        trello=TrelloSettings(
            api_key=_require_env("TRELLO_KEY"),
            token=_require_env("TRELLO_TOKEN"),
            board_id=_require_env("TRELLO_BOARD_ID"),
            list_id=_require_env("TRELLO_LIST_ID"),
        ),
        slack=SlackSettings(
            webhook_url=_optional_env("SLACK_WEBHOOK_URL"),
            bot_token=_optional_env("SLACK_BOT_TOKEN"),
            target_user=_optional_env("SLACK_TARGET_USER"),
        ),
        google=GoogleSettings(
            project_id=_require_env("GOOGLE_PROJECT_ID"),
            client_email=_require_env("GOOGLE_CLIENT_EMAIL"),
            private_key=google_private_key,
            sheet_id=_require_env("GOOGLE_SHEET_ID"),
            worksheet=_optional_env("GOOGLE_SHEET_WORKSHEET"),
            private_key_id=_optional_env("GOOGLE_PRIVATE_KEY_ID"),
            client_id=_optional_env("GOOGLE_CLIENT_ID"),
            token_uri=_optional_env("GOOGLE_TOKEN_URI") or "https://oauth2.googleapis.com/token",
            auth_uri=_optional_env("GOOGLE_AUTH_URI") or "https://accounts.google.com/o/oauth2/auth",
            auth_provider_x509_cert_url=_optional_env("GOOGLE_AUTH_PROVIDER_X509_CERT_URL")
            or "https://www.googleapis.com/oauth2/v1/certs",
            client_x509_cert_url=_optional_env("GOOGLE_CLIENT_X509_CERT_URL"),
            universe_domain=_optional_env("GOOGLE_UNIVERSE_DOMAIN") or "googleapis.com",
        ),
    )


__all__ = [
    "GoogleSettings",
    "ScraperSettings",
    "Settings",
    "SlackSettings",
    "TrelloSettings",
    "get_settings",
]
