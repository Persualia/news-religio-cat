"""Google Sheets repository for tracking processed news items."""
from __future__ import annotations

import logging
from typing import Sequence, TYPE_CHECKING

try:  # pragma: no cover - import guard for optional dependency
    import gspread
except ImportError:  # pragma: no cover
    gspread = None  # type: ignore[assignment]

try:  # pragma: no cover
    from google.oauth2 import service_account
except ImportError:  # pragma: no cover
    service_account = None  # type: ignore[assignment]

from config import GoogleSettings, get_settings
from models import SheetRecord

if TYPE_CHECKING:  # pragma: no cover
    import gspread  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)


class GoogleSheetsRepository:
    """Lightweight repository wrapping gspread interactions."""

    def __init__(self, settings: GoogleSettings | None = None) -> None:
        self._settings = settings or get_settings().google
        self._client: "gspread.Client | None" = None
        self._worksheet: "gspread.Worksheet | None" = None

    # -- Public API ------------------------------------------------------

    def fetch_existing_ids(self) -> set[str]:
        worksheet = self._ensure_worksheet()
        try:
            values = worksheet.col_values(2)  # Column B (ID)
        except gspread.GSpreadException as exc:  # pragma: no cover - defensive
            logger.error("Failed to retrieve IDs from Google Sheet: %s", exc)
            raise

        existing: set[str] = set()
        for value in values:
            trimmed = value.strip()
            if not trimmed or trimmed.lower() == "id":
                continue
            existing.add(trimmed)
        return existing

    def append_records(self, records: Sequence[SheetRecord]) -> None:
        if not records:
            return

        worksheet = self._ensure_worksheet()
        rows = [[record.date, record.doc_id, record.source, record.title] for record in records]
        try:
            worksheet.append_rows(rows, value_input_option="USER_ENTERED")
        except gspread.GSpreadException as exc:  # pragma: no cover - defensive
            logger.error("Failed to append rows to Google Sheet: %s", exc)
            raise

    # -- Internal helpers ------------------------------------------------

    def _ensure_client(self) -> gspread.Client:
        if gspread is None or service_account is None:  # pragma: no cover - defensive branch
            raise RuntimeError("google-auth and gspread are required for Google Sheets integration")
        if self._client is None:
            credentials = service_account.Credentials.from_service_account_info(
                self._build_service_account_info(),
                scopes=SCOPES,
            )
            self._client = gspread.authorize(credentials)
        return self._client

    def _ensure_worksheet(self) -> gspread.Worksheet:
        if self._worksheet is None:
            client = self._ensure_client()
            spreadsheet = client.open_by_key(self._settings.sheet_id)
            if self._settings.worksheet:
                self._worksheet = spreadsheet.worksheet(self._settings.worksheet)
            else:
                self._worksheet = spreadsheet.sheet1
        return self._worksheet

    def _build_service_account_info(self) -> dict[str, str]:
        info = {
            "type": "service_account",
            "project_id": self._settings.project_id,
            "private_key": self._settings.private_key,
            "client_email": self._settings.client_email,
            "token_uri": self._settings.token_uri,
            "auth_uri": self._settings.auth_uri,
        }
        optional_fields = {
            "private_key_id": self._settings.private_key_id,
            "client_id": self._settings.client_id,
            "auth_provider_x509_cert_url": self._settings.auth_provider_x509_cert_url,
            "client_x509_cert_url": self._settings.client_x509_cert_url,
            "universe_domain": self._settings.universe_domain,
        }
        for key, value in optional_fields.items():
            if value:
                info[key] = value
        return info


__all__ = ["GoogleSheetsRepository"]
