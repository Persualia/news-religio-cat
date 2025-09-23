"""Scraper implementation for https://www.maristes.cat/noticies."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup

from models import Article

from .base import BaseScraper


class MaristesScraper(BaseScraper):
    site_id = "maristes"
    base_url = "https://www.maristes.cat"
    listing_url = "https://www.maristes.cat/noticies"
    default_lang = "ca"

    def extract_article_urls(self, listing_soup: BeautifulSoup) -> Iterable[str]:
        seen: set[str] = set()
        for anchor in listing_soup.select("a[href]"):
            href = anchor.get("href", "").strip()
            if not href or href.startswith("#"):
                continue
            if "/noticies/" not in href:
                continue
            if any(segment in href for segment in ("/page/", "/categoria/", "/etiqueta/", "?", "#")):
                continue
            normalized = self._normalize_url(href)
            if normalized.rstrip("/") == self.listing_url.rstrip("/"):
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            yield normalized

    def parse_article(self, article_soup: BeautifulSoup, url: str) -> Article:
        article_node = article_soup.select_one("article") or article_soup.select_one("main") or article_soup

        title = _extract_title(article_node, article_soup)
        if not title:
            raise ValueError("Missing title in article page")

        content_container = _find_content_container(article_node)
        if not content_container:
            content_container = article_node

        paragraphs: list[str] = []
        for element in content_container.find_all(["p", "li"]):
            text = element.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)
        content = "\n\n".join(paragraphs)
        if not content:
            raise ValueError("Article content empty")

        sample_text = " ".join(paragraphs[:5])
        lang = BaseScraper.detect_language(article_soup, [sample_text or content], self.default_lang)

        published_at = _extract_published_at(article_node, article_soup)

        return Article(
            site=self.site_id,
            url=url,
            base_url=self.base_url,
            lang=lang,
            title=title,
            content=content,
            description=None,
            author=None,
            published_at=published_at,
        )


def _find_content_container(article_node: BeautifulSoup) -> BeautifulSoup | None:
    candidates = [
        ".entry-content",
        ".post-content",
        ".single-post-content",
        ".elementor-widget-container",
        ".elementor-widget-theme-post-content",
        ".elementor-post__content",
        "main",
    ]
    for selector in candidates:
        node = article_node.select_one(selector)
        if node and node.get_text(strip=True):
            return node
    return None


_MONTHS_CA = {
    "gen": "Jan",
    "gener": "Jan",
    "feb": "Feb",
    "febrer": "Feb",
    "mar": "Mar",
    "marc": "Mar",
    "març": "Mar",
    "abr": "Apr",
    "abril": "Apr",
    "mai": "May",
    "maig": "May",
    "jun": "Jun",
    "juny": "Jun",
    "jul": "Jul",
    "juliol": "Jul",
    "ago": "Aug",
    "ag": "Aug",
    "agost": "Aug",
    "set": "Sep",
    "setembre": "Sep",
    "oct": "Oct",
    "octubre": "Oct",
    "nov": "Nov",
    "novembre": "Nov",
    "des": "Dec",
    "desembre": "Dec",
}


def _extract_published_at(article_node: BeautifulSoup, article_soup: BeautifulSoup) -> datetime | None:
    for time_tag in article_node.select("time"):
        for attr in ("datetime", "content"):
            candidate = time_tag.get(attr, "").strip()
            parsed = _parse_date(candidate)
            if parsed:
                return parsed
        text = time_tag.get_text(strip=True)
        parsed = _parse_date(text)
        if parsed:
            return parsed

    meta = article_soup.find("meta", attrs={"property": "article:published_time"})
    if meta:
        parsed = _parse_date(meta.get("content", ""))
        if parsed:
            return parsed
    meta = article_soup.find("meta", attrs={"name": "date"})
    if meta:
        parsed = _parse_date(meta.get("content", ""))
        if parsed:
            return parsed
    return None


def _parse_date(value: str) -> datetime | None:
    cleaned = value.strip()
    if not cleaned:
        return None

    iso_candidate = cleaned.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_candidate)
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc)
        else:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    lowered = cleaned.lower()
    lowered = lowered.replace(" de ", " ")
    lowered = re.sub(r"[,\u202f]+", " ", lowered)
    match = re.search(r"(\d{1,2})\s+([a-zà-ÿ]+)\s+(\d{4})", lowered)
    if not match:
        return None
    day = int(match.group(1))
    month_token = match.group(2).strip(".")
    year = int(match.group(3))
    mapped = _MONTHS_CA.get(month_token)
    if not mapped:
        return None
    try:
        dt = datetime.strptime(f"{day}-{mapped}-{year}", "%d-%b-%Y")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


__all__ = ["MaristesScraper"]


def _extract_fallback_title(article_soup: BeautifulSoup) -> str | None:
    for attrs in (
        {"property": "og:title"},
        {"name": "title"},
        {"name": "twitter:title"},
    ):
        meta = article_soup.find("meta", attrs=attrs)
        if meta:
            content = meta.get("content", "").strip()
            if content:
                return content
    if article_soup.title:
        return article_soup.title.get_text(strip=True)
    return None


def _extract_title(article_node: BeautifulSoup, article_soup: BeautifulSoup) -> str | None:
    for scope in (article_node, article_soup):
        container = scope.select_one("[property='dc:title']")
        if container:
            text = container.get_text(strip=True)
            if text:
                return text

    selectors = [
        "h1",
        ".entry-title",
        ".elementor-heading-title",
        "h2",
        ".elementor-post__title",
    ]
    for selector in selectors:
        node = article_node.select_one(selector) or article_soup.select_one(selector)
        if node:
            text = node.get_text(strip=True)
            if text:
                return text

    return _extract_fallback_title(article_soup)
