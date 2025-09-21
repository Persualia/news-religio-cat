import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def pytest_configure():
    os.environ.setdefault("OPENAI_API_KEY", "test-key")
    os.environ.setdefault("BONSAI_URL", "https://user:pass@example.com")
    os.environ.setdefault("N8N_SUMMARY_ENDPOINT", "https://example.com/webhook")


__all__ = []
