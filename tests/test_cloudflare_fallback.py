import httpx
import pytest
from bs4 import BeautifulSoup

import scraping.base as base_module
from scraping.base import BaseScraper, ScraperBlockedError
from scraping.cloudflare import CloudflareRenderError, CloudflareRenderer, unwrap_rendered_content


class _Scraper(BaseScraper):
    site_id = "dummy"
    base_url = "https://example.org"
    listing_url = "https://example.org/news"

    def extract_items(self, listing_soup: BeautifulSoup):
        return []


class _FakeRenderer:
    def __init__(self, body="<html><body>ok</body></html>", content_type="text/html", error=None):
        self.calls: list[str] = []
        self._body = body
        self._content_type = content_type
        self._error = error

    def fetch(self, url):
        self.calls.append(url)
        if self._error:
            raise self._error
        return httpx.Response(
            200,
            headers={"content-type": self._content_type},
            content=self._body.encode(),
            request=httpx.Request("GET", url),
        )


def _scraper(handler, renderer=None) -> _Scraper:
    scraper = _Scraper()
    scraper._client = httpx.Client(transport=httpx.MockTransport(handler))
    scraper._cloudflare = renderer
    scraper._max_retries = 1
    return scraper


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(base_module.time, "sleep", lambda _s: None)


@pytest.mark.parametrize("status", [403, 429, 503])
def test_blocked_status_falls_back_to_cloudflare(status):
    renderer = _FakeRenderer(body='{"ok": true}', content_type="application/json")
    scraper = _scraper(lambda request: httpx.Response(status, request=request), renderer)

    response = scraper._get("https://example.org/api")

    assert response.json() == {"ok": True}
    assert renderer.calls == ["https://example.org/api"]


def test_waf_challenge_falls_back_and_later_requests_prefer_cloudflare():
    origin_calls: list[str] = []

    def handler(request):
        origin_calls.append(str(request.url))
        return httpx.Response(202, headers={"x-amzn-waf-action": "challenge"}, request=request)

    renderer = _FakeRenderer()
    scraper = _scraper(handler, renderer)

    scraper._get("https://example.org/sitemap.xml")
    scraper._get("https://example.org/article")

    assert renderer.calls == ["https://example.org/sitemap.xml", "https://example.org/article"]
    assert origin_calls == ["https://example.org/sitemap.xml"]


def test_not_found_does_not_fall_back():
    renderer = _FakeRenderer()
    scraper = _scraper(lambda request: httpx.Response(404, request=request), renderer)

    with pytest.raises(httpx.HTTPStatusError):
        scraper._get("https://example.org/missing")
    assert renderer.calls == []


def test_original_error_is_raised_when_cloudflare_fails():
    renderer = _FakeRenderer(error=CloudflareRenderError("boom"))
    scraper = _scraper(
        lambda request: httpx.Response(200, headers={"x-amzn-waf-action": "challenge"}, request=request),
        renderer,
    )

    with pytest.raises(ScraperBlockedError, match="AWS WAF"):
        scraper._get("https://example.org/sitemap.xml")


def test_no_fallback_without_credentials():
    scraper = _scraper(lambda request: httpx.Response(403, request=request), renderer=None)

    with pytest.raises(httpx.HTTPStatusError):
        scraper._get("https://example.org/feed")


def test_fallback_can_be_disabled_per_scraper():
    renderer = _FakeRenderer()
    scraper = _scraper(lambda request: httpx.Response(403, request=request), renderer)
    scraper.cloudflare_fallback = False

    with pytest.raises(httpx.HTTPStatusError):
        scraper._get("https://example.org/feed")
    assert renderer.calls == []


def test_cloudflare_response_still_blocked_is_rejected():
    renderer = _FakeRenderer()
    scraper = _scraper(lambda request: httpx.Response(403, request=request), renderer)
    scraper._detect_block = lambda url, response: "still a challenge"

    with pytest.raises(httpx.HTTPStatusError):
        scraper._get("https://example.org/feed")


# -- unwrap_rendered_content ---------------------------------------------

_CHROME_PRE = (
    '<html><head><meta name="color-scheme" content="light dark"></head>'
    '<body><pre style="word-wrap: break-word; white-space: pre-wrap;">{}</pre></body></html>'
)


def test_unwrap_json():
    body, content_type = unwrap_rendered_content(_CHROME_PRE.format('[{"link":"https:\\/\\/x"}]'))
    assert content_type == "application/json"
    assert body == '[{"link":"https:\\/\\/x"}]'


def test_unwrap_escaped_rss():
    body, content_type = unwrap_rendered_content(
        _CHROME_PRE.format("&lt;?xml version=\"1.0\"?&gt;&lt;rss&gt;&lt;item&gt;A &amp;amp; B&lt;/item&gt;&lt;/rss&gt;")
    )
    assert content_type == "application/xml"
    assert body == '<?xml version="1.0"?><rss><item>A &amp; B</item></rss>'


def test_unwrap_raw_xml_passthrough():
    xml = '<?xml-stylesheet type="text/xsl" href="/s.xsl"?><urlset><url><loc>https://x</loc></url></urlset>'
    assert unwrap_rendered_content(xml) == (xml, "application/xml")


def test_unwrap_regular_html_untouched():
    html = "<html><head><title>x</title></head><body><pre>code</pre><p>text</p></body></html>"
    body, content_type = unwrap_rendered_content(html)
    assert body == html
    assert content_type.startswith("text/html")


# -- CloudflareRenderer --------------------------------------------------


def _renderer(handler) -> CloudflareRenderer:
    renderer = CloudflareRenderer("acc", "tok")
    renderer._client = httpx.Client(transport=httpx.MockTransport(handler))
    return renderer


def test_renderer_retries_after_navigation_error():
    payloads = []

    def handler(request):
        import json

        payloads.append(json.loads(request.content))
        if len(payloads) == 1:
            return httpx.Response(
                422,
                json={"success": False, "errors": [{"code": 6000, "message": "x",
                                                    "detail": "Execution context was destroyed, most likely because of a navigation."}]},
            )
        return httpx.Response(200, json={"success": True, "result": _CHROME_PRE.format("[]")})

    response = _renderer(handler).fetch("https://example.org/api")

    assert response.json() == []
    assert payloads[1]["waitForTimeout"] == 5000


def test_renderer_raises_on_api_error():
    renderer = _renderer(
        lambda request: httpx.Response(401, json={"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]})
    )

    with pytest.raises(CloudflareRenderError, match="Authentication error"):
        renderer.fetch("https://example.org")


def test_empty_listing_via_cloudflare_reports_original_error():
    # e.g. a site in maintenance: the 503 is real and Cloudflare just gets the maintenance page.
    renderer = _FakeRenderer(body="<html><body>El web està en manteniment</body></html>")
    scraper = _scraper(lambda request: httpx.Response(503, request=request), renderer)

    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        scraper.scrape()
    assert excinfo.value.response.status_code == 503


def test_tls_errors_do_not_fall_back():
    def handler(request):
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED]", request=request)

    renderer = _FakeRenderer()
    scraper = _scraper(handler, renderer)

    with pytest.raises(httpx.ConnectError):
        scraper._get("https://example.org/feed")
    assert renderer.calls == []


def test_timeouts_fall_back():
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    renderer = _FakeRenderer()
    scraper = _scraper(handler, renderer)

    assert scraper._get("https://example.org/feed").status_code == 200
