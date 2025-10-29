import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def pytest_configure():
    os.environ.setdefault("TRELLO_KEY", "test-trello-key")
    os.environ.setdefault("TRELLO_TOKEN", "test-trello-token")
    os.environ.setdefault("TRELLO_BOARD_ID", "test-board")
    os.environ.setdefault("TRELLO_LIST_ID", "test-list")
    os.environ.setdefault("GOOGLE_PROJECT_ID", "test-project")
    os.environ.setdefault("GOOGLE_CLIENT_EMAIL", "test@example.com")
    os.environ.setdefault(
        "GOOGLE_PRIVATE_KEY",
        "-----BEGIN PRIVATE KEY-----\nTEST\n-----END PRIVATE KEY-----\n",
    )
    os.environ.setdefault("GOOGLE_SHEET_ID", "test-sheet")


__all__ = []
