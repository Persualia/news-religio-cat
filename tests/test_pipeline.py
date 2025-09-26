from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from models import Article
from pipeline.ingestion import DailyPipeline


class StubScraper:
    def __init__(self, article: Article) -> None:
        self._article = article
        self.site_id = article.site

    def scrape(self, limit=None):  # noqa: D401
        """Return a deterministic list of articles for testing."""
        return [self._article]


@pytest.fixture(autouse=True)
def patch_pipeline(monkeypatch):
    mocks = {
        "ensure_collections": Mock(),
        "index_articles": Mock(),
        "index_chunks": Mock(),
        "post_summary": Mock(),
        "find_existing_article_ids": Mock(return_value=set()),
    }
    monkeypatch.setattr("pipeline.ingestion.ensure_collections", mocks["ensure_collections"])
    monkeypatch.setattr("pipeline.ingestion.index_articles", mocks["index_articles"])
    monkeypatch.setattr("pipeline.ingestion.index_chunks", mocks["index_chunks"])
    monkeypatch.setattr("pipeline.ingestion.post_summary", mocks["post_summary"])
    monkeypatch.setattr("pipeline.ingestion.find_existing_article_ids", mocks["find_existing_article_ids"])
    return mocks


def test_pipeline_run_success(patch_pipeline):
    article = Article(
        site="salesians",
        url="https://example.com/news/1",
        base_url="https://example.com",
        lang="ca",
        title="Títol",
        content="Contingut de prova amb informació rellevant.",
        published_at=datetime(2024, 5, 12, tzinfo=timezone.utc),
    )

    embedder = Mock(return_value=[[0.1, 0.2, 0.3]])
    summarizer = Mock(return_value="Resum de prova")
    summary_poster = Mock()

    pipeline = DailyPipeline(
        scrapers=[StubScraper(article)],
        client=Mock(),
        embedder=embedder,
        summarizer=summarizer,
        summary_poster=summary_poster,
    )

    result = pipeline.run()

    assert result.articles_indexed == 1
    assert result.chunks_indexed == 1
    assert result.summary == "Resum de prova"
    embedder.assert_called_once()
    summarizer.assert_called_once()
    summary_poster.assert_called_once_with("Resum de prova")
    patch_pipeline["ensure_collections"].assert_called_once()
    patch_pipeline["index_articles"].assert_called_once()
    patch_pipeline["index_chunks"].assert_called_once()


def test_pipeline_run_handles_summary_post_failure(patch_pipeline):
    article = Article(
        site="salesians",
        url="https://example.com/news/1",
        base_url="https://example.com",
        lang="ca",
        title="Títol",
        content="Contingut curt",
    )

    embedder = Mock(return_value=[[0.1]])
    summarizer = Mock(return_value="Resum de prova")
    summary_poster = Mock(side_effect=RuntimeError("n8n down"))

    pipeline = DailyPipeline(
        scrapers=[StubScraper(article)],
        client=Mock(),
        embedder=embedder,
        summarizer=summarizer,
        summary_poster=summary_poster,
    )

    result = pipeline.run()

    assert result.summary == "Resum de prova"
    summary_poster.assert_called_once()


def test_pipeline_dry_run_skips_external_calls(patch_pipeline):
    article = Article(
        site="salesians",
        url="https://example.com/news/1",
        base_url="https://example.com",
        lang="ca",
        title="Títol",
        content="Contingut curt",
    )

    embedder = Mock(return_value=[[0.1]])
    summarizer = Mock()
    summary_poster = Mock()

    pipeline = DailyPipeline(
        scrapers=[StubScraper(article)],
        client=Mock(),
        embedder=embedder,
        summarizer=summarizer,
        summary_poster=summary_poster,
    )

    result = pipeline.run(dry_run=True)

    assert result.summary == "Dry run: summary not generated"
    embedder.assert_not_called()
    summarizer.assert_not_called()
    summary_poster.assert_not_called()
    patch_pipeline["ensure_collections"].assert_not_called()
    patch_pipeline["index_articles"].assert_not_called()
    patch_pipeline["index_chunks"].assert_not_called()


def test_pipeline_skip_indexing_calls_summary(patch_pipeline):
    article = Article(
        site="salesians",
        url="https://example.com/news/1",
        base_url="https://example.com",
        lang="ca",
        title="Títol",
        content="Contingut curt",
    )

    embedder = Mock(return_value=[[0.1]])
    summarizer = Mock(return_value="Resum de prova")
    summary_poster = Mock()

    pipeline = DailyPipeline(
        scrapers=[StubScraper(article)],
        client=Mock(),
        embedder=embedder,
        summarizer=summarizer,
        summary_poster=summary_poster,
    )

    result = pipeline.run(skip_indexing=True)

    assert result.summary == "Resum de prova"
    assert result.articles_indexed == 0
    assert result.chunks_indexed == 0
    summary_poster.assert_called_once()
    patch_pipeline["ensure_collections"].assert_not_called()
    patch_pipeline["index_articles"].assert_not_called()
    patch_pipeline["index_chunks"].assert_not_called()
