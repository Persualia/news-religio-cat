"""Scraper implementation for https://iqs.edu/ca/iqs/noticies/."""
from __future__ import annotations

import logging
from typing import Iterable

import httpx
from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper
from .feed_utils import extract_text, format_iso, parse_rfc822_datetime


logger = logging.getLogger(__name__)


class IQSScraper(BaseScraper):
    site_id = "iqs"
    base_url = "https://iqs.edu"
    listing_url = "https://iqs.edu/ca/iqs/noticies/feed/"
    default_lang = "ca"

    def __init__(self) -> None:
        super().__init__()
        self._insecure_client = httpx.Client(
            headers=self._client.headers,
            timeout=self._request_timeout,
            follow_redirects=True,
            verify=False,
        )

    def _get_soup(self, url: str) -> BeautifulSoup:
        response = self._get(url)
        return BeautifulSoup(response.text, "xml")

    def _get(self, url: str) -> httpx.Response:
        try:
            return super()._get(url)
        except httpx.ConnectError as exc:
            if not self._is_certificate_verify_failure(exc):
                raise

            logger.warning(
                "Scraper '%s' hit TLS certificate verification failure for %s; retrying with verify=False",
                self.site_id,
                url,
            )
            response = self._insecure_client.get(url)
            response.raise_for_status()
            return response

    @staticmethod
    def _is_certificate_verify_failure(exc: httpx.ConnectError) -> bool:
        text = str(exc)
        if "CERTIFICATE_VERIFY_FAILED" in text:
            return True

        cause = exc.__cause__
        if cause is not None and "CERTIFICATE_VERIFY_FAILED" in repr(cause):
            return True
        return False

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        seen: set[str] = set()

        for entry in listing_soup.select("item"):
            link = extract_text(entry.select_one("link"))
            if not link:
                continue

            normalized = self._normalize_url(link)
            if normalized in seen:
                continue
            seen.add(normalized)

            title = extract_text(entry.select_one("title"))
            if not title:
                continue

            summary_node = entry.find("content:encoded")
            summary = extract_text(summary_node) or extract_text(entry.select_one("description")) or normalized

            pub_node = entry.select_one("pubDate")
            published_at = parse_rfc822_datetime(pub_node.get_text(strip=True) if pub_node else None)

            metadata = {"base_url": self.base_url, "lang": self.default_lang}
            if published_at:
                metadata["published_at"] = format_iso(published_at)

            items.append(
                NewsItem(
                    source=self.site_id,
                    title=title,
                    url=normalized,
                    summary=summary,
                    published_at=published_at or utcnow(),
                    metadata=metadata,
                )
            )

        return items


__all__ = ["IQSScraper"]
