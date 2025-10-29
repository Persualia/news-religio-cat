"""External integrations used by the news ingestion pipeline."""

from .google_sheets import GoogleSheetsRepository
from .slack import SlackNotifier
from .trello import TrelloClient

__all__ = ["GoogleSheetsRepository", "SlackNotifier", "TrelloClient"]
