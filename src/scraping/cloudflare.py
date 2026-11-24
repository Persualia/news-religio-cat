"""Fetch pages through Cloudflare Browser Rendering when an origin blocks us.

Render's shared outbound IPs get bot-blocked by some origins (AWS WAF, rate
limits, 403s). Cloudflare Browser Rendering loads the URL in a headless Chrome
running on Cloudflare's network, so the origin sees Cloudflare's IPs instead.

The REST endpoint only returns the rendered DOM, not the origin's status code
or headers, so JSON/XML responses come back wrapped in Chrome's raw-text viewer
(``<html><body><pre>…</pre></body></html>``). ``fetch`` unwraps that and
returns an ``httpx.Response`` that the scrapers can consume as if it came
straight from the origin.
"""
from __future__ import annotations

import json
import logging
import time

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_API_URL = "https://api.cloudflare.com/client/v4/accounts/{account_id}/browser-rendering/content"

# Pages that navigate on their own (e.g. Anubis proof-of-work challenges reload
# the page once solved) make the default render fail with this error. Retrying
# with a quiet-network wait plus a fixed delay lets the redirect settle.
_NAVIGATION_ERROR = "Execution context was destroyed"


class CloudflareRenderError(RuntimeError):
    """Raised when Cloudflare Browser Rendering cannot return the page."""


class CloudflareRenderer:
    def __init__(self, account_id: str, api_token: str, *, timeout: float = 90.0) -> None:
        self._endpoint = _API_URL.format(account_id=account_id)
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=timeout,
        )

    def fetch(self, url: str) -> httpx.Response:
        try:
            html = self._render(url, {"gotoOptions": {"waitUntil": "networkidle2", "timeout": 45000}})
        except CloudflareRenderError as exc:
            if _NAVIGATION_ERROR not in str(exc):
                raise
            logger.info("Cloudflare render of %s navigated mid-render; retrying with a settle delay", url)
            html = self._render(
                url,
                {"gotoOptions": {"waitUntil": "networkidle0", "timeout": 60000}, "waitForTimeout": 5000},
            )
        body, content_type = unwrap_rendered_content(html)
        return httpx.Response(
            200,
            headers={"content-type": content_type, "x-fetched-via": "cloudflare-browser-rendering"},
            content=body.encode("utf-8"),
            request=httpx.Request("GET", url),
        )

    def _render(self, url: str, options: dict) -> str:
        payload = {"url": url, **options}
        for attempt in (1, 2):
            try:
                response = self._client.post(self._endpoint, json=payload)
            except httpx.HTTPError as exc:
                raise CloudflareRenderError(f"Cloudflare request failed for {url}: {exc}") from exc

            if response.status_code == 429 and attempt == 1:
                wait = _retry_after_seconds(response)
                logger.info("Cloudflare Browser Rendering rate limited; retrying in %.0fs", wait)
                time.sleep(wait)
                continue

            try:
                data = response.json()
            except ValueError as exc:
                raise CloudflareRenderError(
                    f"Cloudflare returned HTTP {response.status_code} with non-JSON body for {url}"
                ) from exc

            if not data.get("success"):
                errors = "; ".join(
                    f"{err.get('code')}: {err.get('detail') or err.get('message')}"
                    for err in data.get("errors") or []
                )
                raise CloudflareRenderError(
                    f"Cloudflare HTTP {response.status_code} rendering {url}: {errors or 'unknown error'}"
                )
            return data.get("result") or ""
        raise CloudflareRenderError(f"Cloudflare rate limit persisted for {url}")


def unwrap_rendered_content(html: str) -> tuple[str, str]:
    """Return ``(body, content_type)`` for a DOM returned by Browser Rendering.

    Non-HTML documents (JSON, RSS, plain text) are shown by Chrome as a single
    ``<pre>`` inside an otherwise empty body; we extract its text. Raw XML that
    Chrome serialises as-is (e.g. sitemaps with an XSL stylesheet) is passed
    through untouched.
    """
    stripped = html.lstrip()
    if stripped.startswith("<?xml"):
        return html, "application/xml"

    soup = BeautifulSoup(html, "lxml")
    body = soup.body
    if body is not None:
        children = [child for child in body.children if getattr(child, "name", None)]
        if children and children[0].name == "pre" and soup.select_one('meta[name="color-scheme"]'):
            text = children[0].get_text()
            return text, _guess_text_content_type(text)

    return html, "text/html; charset=utf-8"


def _guess_text_content_type(text: str) -> str:
    candidate = text.lstrip()
    if candidate[:1] in ("{", "["):
        try:
            json.loads(candidate)
        except ValueError:
            pass
        else:
            return "application/json"
    if candidate.startswith("<"):
        return "application/xml"
    return "text/plain; charset=utf-8"


def _retry_after_seconds(response: httpx.Response) -> float:
    try:
        return min(max(float(response.headers.get("retry-after", "")), 1.0), 30.0)
    except ValueError:
        return 10.0


__all__ = ["CloudflareRenderError", "CloudflareRenderer", "unwrap_rendered_content"]
