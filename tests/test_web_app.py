import importlib

from fastapi.testclient import TestClient

from pipeline.ingestion import PipelineResult
from web.app import app, run_daily_lock

web_app_module = importlib.import_module("web.app")


class StubPipeline:
    init_scrapers = None
    run_kwargs = None

    def __init__(self, *, scrapers=None, trello_client=None, sheets_repo=None, slack_notifier=None):
        type(self).init_scrapers = scrapers

    def run(self, **kwargs):
        type(self).run_kwargs = kwargs
        return PipelineResult(
            sources_processed=2,
            total_items=7,
            new_items=3,
            skipped_existing=4,
            skipped_stale=0,
            alerts_sent=1,
            live=kwargs["live_run"],
        )


def test_healthz_returns_ok():
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_run_daily_requires_valid_basic_auth(monkeypatch):
    monkeypatch.setenv("RUN_DAILY_USERNAME", "runner")
    monkeypatch.setenv("RUN_DAILY_PASSWORD", "secret")

    client = TestClient(app)
    response = client.post("/run-daily", auth=("runner", "wrong"))

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"


def test_run_daily_executes_pipeline(monkeypatch):
    monkeypatch.setenv("RUN_DAILY_USERNAME", "runner")
    monkeypatch.setenv("RUN_DAILY_PASSWORD", "secret")
    monkeypatch.setattr(web_app_module, "TrelloPipeline", StubPipeline)
    monkeypatch.setattr(
        web_app_module,
        "instantiate_scrapers",
        lambda site_ids: [f"scraper:{site_id}" for site_id in site_ids],
    )

    client = TestClient(app)
    response = client.post(
        "/run-daily",
        auth=("runner", "secret"),
        json={"dry_run": True, "limit_per_site": 5, "sites": ["salesians", "jesuites"]},
    )

    assert response.status_code == 200
    assert response.json()["new_items"] == 3
    assert StubPipeline.init_scrapers == ["scraper:salesians", "scraper:jesuites"]
    assert StubPipeline.run_kwargs == {
        "limit_per_site": 5,
        "dry_run": True,
        "live_run": True,
    }


def test_run_daily_returns_conflict_when_already_running(monkeypatch):
    monkeypatch.setenv("RUN_DAILY_USERNAME", "runner")
    monkeypatch.setenv("RUN_DAILY_PASSWORD", "secret")

    client = TestClient(app)
    acquired = run_daily_lock.acquire(blocking=False)
    assert acquired is True
    try:
        response = client.post("/run-daily", auth=("runner", "secret"))
    finally:
        run_daily_lock.release()

    assert response.status_code == 409
    assert response.json()["detail"] == "run_daily is already in progress."
