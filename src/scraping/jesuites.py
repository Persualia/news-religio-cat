"""Scraper implementation for https://jesuites.net/ca/totes-les-noticies."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup

from models import Article

from .base import BaseScraper


class JesuitesScraper(BaseScraper):
    site_id = "jesuites"
    base_url = "https://jesuites.net"
    listing_url = "https://jesuites.net/ca/totes-les-noticies"
    default_lang = "ca"

    def extract_article_urls(self, listing_soup: BeautifulSoup) -> Iterable[str]:
        seen: set[str] = set()
        for node in listing_soup.select(".gva-view-grid .node--type-noticia"):
            anchor = node.select_one(".post-title a[href]")
            if not anchor:
                continue
            href = anchor.get("href", "").strip()
            if not href or href in seen:
                continue
            seen.add(href)
            yield href

    def parse_article(self, article_soup: BeautifulSoup, url: str) -> Article:
        article_node = article_soup.select_one("article.node--type-noticia") or article_soup

        title_tag = article_node.select_one("h1.post-title") or article_node.find("h1")
        if not title_tag:
            raise ValueError("Missing title in article page")
        title = title_tag.get_text(strip=True)

        content_container = article_node.select_one(".node__content") or article_node
        paragraphs: list[str] = []
        for element in content_container.find_all(["p", "li"]):
            text = element.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)
        content = "\n\n".join(paragraphs)
        if not content:
            raise ValueError("Article content empty")

        description = _extract_description(article_soup)

        sample_text = " ".join(paragraphs[:5])
        if description:
            sample_text = f"{description} {sample_text}".strip()
        lang = BaseScraper.detect_language(article_soup, [sample_text or content], self.default_lang)

        published_at = _extract_published_at(article_node, article_soup)
        author = _extract_author(article_node, article_soup)

        return Article(
            site=self.site_id,
            url=url,
            base_url=self.base_url,
            lang=lang,
            title=title,
            content=content,
            description=description,
            author=author,
            published_at=published_at,
        )


def _extract_description(article_soup: BeautifulSoup) -> str | None:
    meta = article_soup.find("meta", attrs={"property": "og:description"}) or article_soup.find(
        "meta", attrs={"name": "description"}
    )
    if meta:
        content = meta.get("content", "").strip()
        if content:
            return content
    return None


def _extract_author(article_node: BeautifulSoup, article_soup: BeautifulSoup) -> str | None:
    author_tag = article_node.select_one(".post-author")
    if author_tag:
        author_text = author_tag.get_text(strip=True)
        if author_text:
            return author_text
    meta = article_soup.find("meta", attrs={"name": "author"})
    if meta:
        content = meta.get("content", "").strip()
        if content:
            return content
    return None


_MONTH_MAP = {
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
    date_tag = article_node.select_one(".post-meta .post-created")
    if date_tag:
        parsed = _parse_date(date_tag.get_text(strip=True))
        if parsed:
            return parsed
    meta = article_soup.find("meta", attrs={"property": "article:published_time"})
    if meta:
        parsed = _parse_date(meta.get("content", ""))
        if parsed:
            return parsed
    return None


def _parse_date(value: str) -> datetime | None:
    cleaned = value.strip()
    if not cleaned:
        return None

    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    normalized = cleaned.lower()
    normalized = normalized.replace(" de ", " ")
    parts = [part for part in normalized.replace(",", " ").split() if part]
    if len(parts) >= 3 and parts[0].isdigit() and parts[-1].isdigit():
        day = int(parts[0])
        year = int(parts[-1])
        month_token = parts[1].strip(".")
        mapped = _MONTH_MAP.get(month_token)
        if mapped:
            try:
                dt = datetime.strptime(f"{day}-{mapped}-{year}", "%d-%b-%Y")
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
    return None


__all__ = ["JesuitesScraper"]
