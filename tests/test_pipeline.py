from datetime import datetime, timedelta, timezone

from models import NewsItem, utcnow
from pipeline.ingestion import PipelineResult, TrelloPipeline


class StubScraper:
    def __init__(self, site_id: str, items: list[NewsItem]) -> None:
        self.site_id = site_id
        self._items = items

    def scrape(self, limit=None):
        if limit is not None:
            return self._items[:limit]
        return list(self._items)


class StubSheets:
    def __init__(self, existing: set[str] | None = None) -> None:
        self._existing = set(existing or [])
        self.appended: list = []
        self.trimmed_to: int | None = None

    def fetch_existing_ids(self) -> set[str]:
        return set(self._existing)

    def append_records(self, records):
        self.appended.extend(records)
        self._existing.update(record.doc_id for record in records)

    def trim_to_limit(self, max_rows: int) -> None:
        self.trimmed_to = max_rows


class StubTrello:
    def __init__(self) -> None:
        self.created: list[NewsItem] = []

    def create_card(self, item: NewsItem) -> str:
        self.created.append(item)
        return f"card-{len(self.created)}"


class StubSlack:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.block_messages: list[dict] = []

    def notify(self, message: str) -> None:
        self.messages.append(message)

    def notify_blocks(self, *, blocks, text=None):
        self.block_messages.append({"blocks": blocks, "text": text})


def _news_item(url: str, source: str = "salesians", *, published_at: datetime | None = None) -> NewsItem:
    return NewsItem(
        source=source,
        title=f"Title for {url}",
        url=url,
        author="Author",
        published_at=published_at or utcnow(),
        metadata={"lang": "ca", "base_url": "https://example.com"},
    )


def test_pipeline_creates_cards_for_new_items():
    items = [_news_item("https://example.com/a"), _news_item("https://example.com/b")]
    scrapers = [StubScraper("salesians", items)]
    sheets = StubSheets(existing=set())
    trello = StubTrello()
    slack = StubSlack()

    pipeline = TrelloPipeline(scrapers=scrapers, trello_client=trello, sheets_repo=sheets, slack_notifier=slack)
    result: PipelineResult = pipeline.run(live_run=False)

    assert result.sources_processed == 1
    assert result.new_items == 2
    assert result.live is False
    assert len(trello.created) == 2
    assert len(sheets.appended) == 2
    assert sheets.trimmed_to == 800
    assert result.skipped_stale == 0
    assert not slack.messages
    assert len(slack.block_messages) == 1


def test_pipeline_skips_existing_ids():
    existing = {_news_item("https://example.com/a").doc_id}
    items = [
        _news_item("https://example.com/a"),
        _news_item("https://example.com/b"),
    ]
    scrapers = [StubScraper("salesians", items)]
    sheets = StubSheets(existing=existing)
    trello = StubTrello()
    slack = StubSlack()

    pipeline = TrelloPipeline(scrapers=scrapers, trello_client=trello, sheets_repo=sheets, slack_notifier=slack)
    result = pipeline.run(live_run=False)

    assert result.new_items == 1
    assert result.skipped_existing == 1
    assert result.skipped_stale == 0
    assert len(trello.created) == 1
    assert len(sheets.appended) == 1
    assert sheets.trimmed_to == 800


def test_pipeline_dry_run_avoids_side_effects():
    items = [_news_item("https://example.com/a")]
    scrapers = [StubScraper("salesians", items)]
    sheets = StubSheets()
    trello = StubTrello()
    slack = StubSlack()

    pipeline = TrelloPipeline(scrapers=scrapers, trello_client=trello, sheets_repo=sheets, slack_notifier=slack)
    result = pipeline.run(dry_run=True, live_run=False)

    assert result.live is False
    assert result.new_items == 1
    assert result.skipped_stale == 0
    assert not trello.created
    assert not sheets.appended
    assert sheets.trimmed_to is None
    assert not slack.messages
    assert any("Mode" in field["text"] for field in slack.block_messages[0]["blocks"][1]["fields"])


def test_pipeline_notifies_when_scraper_returns_no_items():
    class EmptyScraper(StubScraper):
        def scrape(self, limit=None):
            from scraping.base import ScraperNoArticlesError

            raise ScraperNoArticlesError(self.site_id)

    scrapers = [EmptyScraper("jesuites", [])]
    sheets = StubSheets()
    trello = StubTrello()
    slack = StubSlack()

    pipeline = TrelloPipeline(scrapers=scrapers, trello_client=trello, sheets_repo=sheets, slack_notifier=slack)
    result = pipeline.run(live_run=False)

    assert result.sources_processed == 0
    assert result.new_items == 0
    assert result.alerts_sent == 1
    assert result.skipped_stale == 0
    assert slack.messages
    assert not trello.created
    assert not sheets.appended
    assert sheets.trimmed_to is None


def test_pipeline_summary_marks_live_runs():
    items = [_news_item("https://example.com/a")]
    scrapers = [StubScraper("salesians", items)]
    sheets = StubSheets()
    trello = StubTrello()
    slack = StubSlack()

    pipeline = TrelloPipeline(scrapers=scrapers, trello_client=trello, sheets_repo=sheets, slack_notifier=slack)
    result = pipeline.run(live_run=True)

    assert result.live is True
    summary_fields = slack.block_messages[0]["blocks"][1]["fields"]
    live_field = next(field for field in summary_fields if "*Live*" in field["text"])
    assert "true" in live_field["text"]


def test_pipeline_skips_stale_items():
    fresh_item = _news_item("https://example.com/fresh", published_at=utcnow())
    stale_item = _news_item(
        "https://example.com/old",
        published_at=utcnow() - timedelta(days=20),
    )
    scrapers = [StubScraper("salesians", [stale_item, fresh_item])]
    sheets = StubSheets()
    trello = StubTrello()
    slack = StubSlack()

    pipeline = TrelloPipeline(scrapers=scrapers, trello_client=trello, sheets_repo=sheets, slack_notifier=slack)
    result = pipeline.run(live_run=False)

    assert result.new_items == 1
    assert result.skipped_stale == 1
    assert len(trello.created) == 1
    assert len(sheets.appended) == 1
