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
    monkeypatch.setattr("pipeline.ingestion.ensure_templates", Mock(return_value=True))
    monkeypatch.setattr(
        "pipeline.ingestion.ensure_monthly_indices",
        Mock(return_value=("articles-2024.05", "chunks-2024.05")),
    )
    monkeypatch.setattr("pipeline.ingestion.index_articles", Mock())
    monkeypatch.setattr("pipeline.ingestion.index_chunks", Mock())
    monkeypatch.setattr("pipeline.ingestion.post_summary", Mock())
    yield


def test_pipeline_run_success():
    article = Article(
        site="salesians",
        url="https://example.com/news/1",
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


def test_pipeline_run_handles_summary_post_failure():
    article = Article(
        site="salesians",
        url="https://example.com/news/1",
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


def test_pipeline_dry_run_skips_external_calls():
    article = Article(
        site="salesians",
        url="https://example.com/news/1",
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
