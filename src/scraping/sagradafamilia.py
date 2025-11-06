"""Scraper implementation for https://sagradafamilia.org/actualitat."""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Iterable
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from models import NewsItem, utcnow

from .base import BaseScraper

_AUTH_TOKEN_RE = re.compile(r'Liferay\.authToken\s*=\s*"(?P<token>[^"]+)"')
_PLID_RE = re.compile(r"getPlid:function\(\)\{return\"(?P<plid>\d+)\"")
_PORTLET_ID = "com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_2yfH8wNJ7HD2"
_PORTLET_PARAM_PREFIX = "_com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_2yfH8wNJ7HD2"


class SagradaFamiliaScraper(BaseScraper):
    site_id = "sagradafamilia"
    base_url = "https://sagradafamilia.org"
    listing_url = "https://sagradafamilia.org/actualitat"
    default_lang = "ca"

    def extract_items(self, listing_soup: BeautifulSoup) -> Iterable[NewsItem]:
        auth_token = _extract_auth_token(listing_soup)
        plid = _extract_plid(listing_soup)

        portlet_soup = listing_soup
        if auth_token and plid:
            try:
                portlet_soup = self._fetch_portlet(plid, auth_token)
            except Exception:  # noqa: BLE001
                portlet_soup = listing_soup

        items: list[NewsItem] = []
        seen: set[str] = set()

        for entry in portlet_soup.select(".asset-abstract"):
            anchor = entry.select_one(".asset-title a[href]")
            if anchor is None:
                continue
            href = anchor.get("href", "").strip()
            if not href:
                continue

            if "?redirect=" in href:
                href = href.split("?redirect=", 1)[0]

            normalized = self._normalize_url(href)
            if normalized in seen:
                continue
            seen.add(normalized)

            title = anchor.get_text(strip=True)
            if not title:
                continue

            date_node = entry.select_one(".metadata-publish-date")
            published_at = _parse_date(date_node.get_text(strip=True) if date_node else "")

            metadata = {"base_url": self.base_url, "lang": self.default_lang}
            if published_at:
                metadata["published_at"] = _format_iso(published_at)

            items.append(
                NewsItem(
                    source=self.site_id,
                    title=title,
                    url=normalized,
                    summary=normalized,
                    published_at=published_at or utcnow(),
                    metadata=metadata,
                )
            )

        return items

    def _fetch_portlet(self, plid: str, auth_token: str) -> BeautifulSoup:
        params = {
            "p_l_id": plid,
            "p_p_id": _PORTLET_ID,
            "p_p_lifecycle": 2,
            "p_p_state": "normal",
            "p_p_mode": "view",
            "p_p_cacheability": "cacheLevelPage",
            f"{_PORTLET_PARAM_PREFIX}_cur": 1,
            f"{_PORTLET_PARAM_PREFIX}_delta": 20,
            "p_auth": auth_token,
        }
        url = f"{self.base_url}/c/portal/render_portlet?{urlencode(params)}"
        response = self._get(url)
        return BeautifulSoup(response.text, "lxml")


def _extract_auth_token(soup: BeautifulSoup) -> str | None:
    scripts = soup.find_all("script")
    for script in scripts:
        content = script.string or ""
        match = _AUTH_TOKEN_RE.search(content)
        if match:
            return match.group("token")
    return None


def _extract_plid(soup: BeautifulSoup) -> str | None:
    scripts = soup.find_all("script")
    for script in scripts:
        content = script.string or ""
        match = _PLID_RE.search(content)
        if match:
            return match.group("plid")
    return None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(cleaned, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _format_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


__all__ = ["SagradaFamiliaScraper"]
