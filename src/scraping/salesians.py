"""Scraper implementation for https://www.salesians.cat/noticies/."""
from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata
from typing import Iterable

from bs4 import BeautifulSoup

from models import Article

from .base import BaseScraper


class SalesiansScraper(BaseScraper):
    site_id = "salesians"
    base_url = "https://www.salesians.cat"
    listing_url = "https://www.salesians.cat/noticies/"
    default_lang = "ca"

    def extract_article_urls(self, listing_soup: BeautifulSoup) -> Iterable[str]:
        seen: set[str] = set()
        for anchor in listing_soup.select("a[href]"):
            href = anchor["href"]
            if not href:
                continue
            if "salesianos.info/blog/" not in href:
                continue
            if "/blog/category/" in href or href.endswith("/category/"):
                continue
            if href in seen:
                continue
            seen.add(href)
            yield href

    def parse_article(self, article_soup: BeautifulSoup, url: str) -> Article:
        article_node = article_soup.select_one("article") or article_soup

        title_tag = (
            article_node.select_one("h1.entry-title")
            or article_node.select_one("header h1")
            or article_soup.select_one(".et_pb_text_inner")
            or article_soup.select_one("h1")
        )
        if not title_tag:
            raise ValueError("Missing title in article page")
        title = title_tag.get_text(strip=True)

        description_tag = (
            article_node.select_one(".entry-summary p")
            or article_node.select_one(".el_single_post_excerpt")
        )
        description = description_tag.get_text(strip=True) if description_tag else None

        body = (
            article_node.select_one(".entry-content")
            or article_soup.select_one(".et_pb_post_content")
            or article_soup.select_one(".entry-content")
        )
        if not body:
            raise ValueError("Missing article body")
        paragraphs = []
        for element in body.find_all(["p", "li"]):
            text = element.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)
        content = "\n\n".join(paragraphs)

        if not content:
            raise ValueError("Article content empty")

        blurb_entries = _extract_blurb_entries(article_node)
        if not blurb_entries and article_node is not article_soup:
            blurb_entries = _extract_blurb_entries(article_soup)
        description_candidate = _guess_description(blurb_entries)
        if description_candidate:
            description = description_candidate

        sample_text = " ".join(paragraphs[:5])
        if description:
            sample_text = f"{description} {sample_text}".strip()
        lang = BaseScraper.detect_language(article_soup, [sample_text or content], self.default_lang)
        author = _guess_author(blurb_entries)

        published_at = None
        time_tag = article_node.find("time")
        if time_tag:
            datetime_attr = time_tag.get("datetime") or time_tag.get_text(strip=True)
            if datetime_attr:
                published_at = _parse_datetime(datetime_attr)
        if not published_at:
            published_node = article_soup.select_one(".published")
            if published_node:
                cleaned = re.sub(r"^[^0-9A-Za-z]+", "", published_node.get_text(strip=True))
                published_at = _parse_datetime(cleaned)
        if not published_at:
            date_text = _guess_date_text(blurb_entries)
            if date_text:
                published_at = _parse_human_date_text(date_text)

        author_tag = (
            article_node.select_one(".author")
            or article_soup.select_one(".entry-author")
            or article_soup.select_one("meta[name='author']")
        )
        if not author and author_tag and author_tag.name == "meta":
            content_value = author_tag.get("content", "").strip()
            author = content_value or None
        elif not author and author_tag:
            author = author_tag.get_text(strip=True)

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


def _parse_datetime(value: str) -> datetime | None:
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%b %d, %Y",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=timezone.utc)
            else:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _extract_blurb_entries(article_node: BeautifulSoup) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for blurb in article_node.select("div.et_pb_module.et_pb_blurb"):
        icon_node = blurb.select_one(".et-pb-icon")
        icon = icon_node.get_text(strip=True) if icon_node else ""
        header = blurb.select_one(".et_pb_module_header span") or blurb.select_one(".et_pb_module_header")
        text = header.get_text(strip=True) if header else ""
        if text:
            entries.append((icon, text))
    return entries


DATE_ICONS = {"", "", ""}
AUTHOR_ICONS = {"", "", ""}
DATE_REGEX = re.compile(r"(\d{1,2})\s+(?:de\s+)?([A-Za-zÀ-ÿ]+)\s+(?:de\s+)?(\d{4})")


def _guess_description(entries: list[tuple[str, str]]) -> str | None:
    for icon, text in entries:
        if icon in DATE_ICONS or icon in AUTHOR_ICONS:
            continue
        if len(text.split()) >= 6:
            return text
    return None


def _guess_author(entries: list[tuple[str, str]]) -> str | None:
    for icon, text in entries:
        if icon in AUTHOR_ICONS:
            cleaned = text.strip()
            if "|" in cleaned:
                parts = [part.strip() for part in cleaned.split("|") if part.strip()]
                for part in parts:
                    normalized_part = _normalize_token(part)
                    if "opinion" not in normalized_part:
                        cleaned = part
                        break
                else:
                    cleaned = parts[-1]
            for prefix in ("Por ", "Per ", "POR ", "PER ", "Opinión|", "Opinió|"):
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix) :]
            cleaned = cleaned.strip().strip(".")
            return cleaned or None
    return None


def _guess_date_text(entries: list[tuple[str, str]]) -> str | None:
    for icon, text in entries:
        if icon in DATE_ICONS:
            return text
    return None


def _normalize_lang(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower().replace("_", "-")
    if lowered.startswith("ca"):
        return "ca"
    if lowered.startswith("es"):
        return "es"
    return None


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


def _detect_language(soup: BeautifulSoup, text: str, default: str) -> str:
    candidates = [
        soup.html.get("lang") if soup.html else None,
        soup.find("meta", attrs={"property": "og:locale"}),
        soup.find("meta", attrs={"name": "language"}),
        soup.find("meta", attrs={"property": "article:language"}),
    ]

    normalized = None
    for candidate in candidates:
        value = candidate.get("content") if hasattr(candidate, "get") else candidate
        normalized = _normalize_lang(value)
        if normalized:
            break

    lang = normalized or default

    text_lower = text.lower()
    tokens = re.findall(r"[a-zà-ÿ']+", text_lower)
    token_set = set(tokens)

    cat_score = sum(1 for word in CATALAN_MARKERS if word in token_set)
    cat_score += sum(text_lower.count(char) for char in ("à", "è", "ò", "ï", "·"))
    es_score = sum(1 for word in SPANISH_MARKERS if word in token_set)
    es_score += text_lower.count("ción")

    if lang != "ca" and cat_score >= max(2, es_score + 1):
        return "ca"
    if lang != "es" and es_score >= max(2, cat_score + 1):
        return "es"
    return lang


MONTH_MAP = {
    "enero": 1,
    "ener": 1,
    "gener": 1,
    "febrero": 2,
    "febrer": 2,
    "marzo": 3,
    "marc": 3,
    "març": 3,
    "abril": 4,
    "mayo": 5,
    "maig": 5,
    "junio": 6,
    "juny": 6,
    "julio": 7,
    "juliol": 7,
    "agosto": 8,
    "agost": 8,
    "septiembre": 9,
    "setiembre": 9,
    "setembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "novembre": 11,
    "diciembre": 12,
    "desembre": 12,
}


def _parse_human_date_text(value: str) -> datetime | None:
    match = DATE_REGEX.search(value)
    if not match:
        return None
    day_str, month_raw, year_str = match.groups()
    month_key = _normalize_token(month_raw)
    month = MONTH_MAP.get(month_key)
    if not month:
        return None
    try:
        dt = datetime(int(year_str), month, int(day_str), tzinfo=timezone.utc)
    except ValueError:
        return None
    return dt


def _normalize_token(token: str) -> str:
    normalized = unicodedata.normalize("NFKD", token.lower())
    return "".join(ch for ch in normalized if ch.isalpha())


__all__ = ["SalesiansScraper"]
