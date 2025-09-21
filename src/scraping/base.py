"""Abstract base scraper with shared HTTP + parsing helpers."""
from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from typing import Iterable, List, Optional, Sequence
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from config import get_settings
from models import Article


class BaseScraper(ABC):
    """Reusable base class that handles HTTP concerns and orchestration."""

    site_id: str
    base_url: str
    listing_url: str
    default_lang: str = "ca"

    def __init__(self) -> None:
        settings = get_settings().scraper
        self._client = httpx.Client(
            headers={"User-Agent": settings.user_agent},
            timeout=settings.request_timeout,
        )
        self._throttle_seconds = settings.throttle_seconds
        self._max_retries = settings.max_retries

    # -- Template methods -------------------------------------------------

    @abstractmethod
    def extract_article_urls(self, listing_soup: BeautifulSoup) -> Iterable[str]:
        """Return absolute article URLs from the listing soup."""

    @abstractmethod
    def parse_article(self, article_soup: BeautifulSoup, url: str) -> Article:
        """Create an article instance from the article soup."""

    # -- Orchestration ----------------------------------------------------

    def scrape(self, *, limit: Optional[int] = None) -> List[Article]:
        listing_soup = self._get_soup(self.listing_url)
        urls = list(dict.fromkeys(self._normalize_url(url) for url in self.extract_article_urls(listing_soup)))
        if limit:
            urls = urls[:limit]

        articles: list[Article] = []
        for url in urls:
            soup = self._get_soup(url)
            article = self.parse_article(soup, url)
            articles.append(article)
            time.sleep(self._throttle_seconds)
        return articles

    # -- Networking helpers ----------------------------------------------

    def _get(self, url: str) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.get(url)
                response.raise_for_status()
                return response
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                sleep_time = self._throttle_seconds * attempt
                time.sleep(sleep_time)
        if last_exc:
            raise last_exc
        raise RuntimeError(f"Failed to GET {url}")

    def _get_soup(self, url: str) -> BeautifulSoup:
        response = self._get(url)
        return BeautifulSoup(response.text, "lxml")

    def _normalize_url(self, url: str) -> str:
        return urljoin(self.base_url, url)

    # -- Language helpers -------------------------------------------------

    @staticmethod
    def detect_language(
        soup: BeautifulSoup,
        text_samples: Sequence[str],
        default: str = "ca",
    ) -> str:
        """Heuristic language detection for common Romance languages."""

        meta_candidates = [
            soup.html.get("lang") if soup.html else None,
            soup.find("meta", attrs={"property": "og:locale"}),
            soup.find("meta", attrs={"name": "language"}),
            soup.find("meta", attrs={"property": "article:language"}),
        ]

        normalized = None
        for candidate in meta_candidates:
            value = candidate.get("content") if hasattr(candidate, "get") else candidate
            normalized = _normalize_lang(value)
            if normalized:
                break

        lang = normalized or default

        combined = " ".join(filter(None, text_samples)).lower()
        tokens = set(re.findall(r"[a-zà-ÿ']+", combined))

        scores = {
            "ca": _lexical_score(tokens, combined, CATALAN_MARKERS, extra_chars="àèòï·")
            + (2 if lang == "ca" else 0),
            "es": _lexical_score(tokens, combined, SPANISH_MARKERS, extra_terms=["ción"])
            + (2 if lang == "es" else 0),
            "en": _lexical_score(tokens, combined, ENGLISH_MARKERS)
            + (2 if lang == "en" else 0),
            "fr": _lexical_score(tokens, combined, FRENCH_MARKERS)
            + (2 if lang == "fr" else 0),
        }

        best_lang, best_score = max(scores.items(), key=lambda item: item[1])
        if best_score >= 2:
            return best_lang
        return lang


__all__ = ["BaseScraper"]


def _normalize_lang(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower().replace("_", "-")
    if lowered.startswith("ca"):
        return "ca"
    if lowered.startswith("es"):
        return "es"
    if lowered.startswith("en"):
        return "en"
    if lowered.startswith("fr"):
        return "fr"
    return None


def _lexical_score(
    tokens: set[str],
    text: str,
    markers: set[str],
    *,
    extra_chars: str = "",
    extra_terms: Optional[Sequence[str]] = None,
) -> int:
    score = sum(1 for token in markers if token in tokens)
    for char in extra_chars:
        score += text.count(char)
    if extra_terms:
        for term in extra_terms:
            score += text.count(term)
    return score


CATALAN_MARKERS = {
    "amb",
    "aquest",
    "aquesta",
    "aquests",
    "aquestes",
    "perquè",
    "nosaltres",
    "vosaltres",
    "això",
    "així",
    "dels",
    "gairebé",
    "infància",
    "joves",
}


SPANISH_MARKERS = {
    "con",
    "este",
    "esta",
    "estos",
    "estas",
    "porque",
    "nosotros",
    "vosotros",
    "ellos",
    "ellas",
    "jóvenes",
}


ENGLISH_MARKERS = {
    "the",
    "and",
    "with",
    "this",
    "that",
    "from",
    "about",
    "during",
    "people",
    "community",
}


FRENCH_MARKERS = {
    "avec",
    "pour",
    "cette",
    "ceci",
    "nous",
    "vous",
    "ainsi",
    "jeunes",
    "communauté",
    "projet",
}
