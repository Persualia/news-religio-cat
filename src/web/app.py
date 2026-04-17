"""Minimal FastAPI control plane for Render-triggered runs."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
import logging
import os
import secrets
import threading
from typing import Annotated

from fastapi import Body, Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from logging_utils import setup_logging
from pipeline import TrelloPipeline
from scraping import instantiate_scrapers

logger = logging.getLogger(__name__)

security = HTTPBasic()
run_daily_lock = threading.Lock()


class RunDailyRequest(BaseModel):
    """Optional controls for manual pipeline runs."""

    dry_run: bool = False
    limit_per_site: int | None = Field(default=None, ge=1)
    sites: list[str] | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    yield


app = FastAPI(title="news-religio-cat", version="1.0.0", lifespan=lifespan)


def _authenticate(credentials: Annotated[HTTPBasicCredentials, Depends(security)]) -> str:
    expected_username = os.getenv("RUN_DAILY_USERNAME")
    expected_password = os.getenv("RUN_DAILY_PASSWORD")

    if not expected_username or not expected_password:
        logger.error("RUN_DAILY basic auth is not configured.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="RUN_DAILY_USERNAME and RUN_DAILY_PASSWORD must be configured.",
        )

    valid_username = secrets.compare_digest(credentials.username, expected_username)
    valid_password = secrets.compare_digest(credentials.password, expected_password)
    if valid_username and valid_password:
        return credentials.username

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials.",
        headers={"WWW-Authenticate": "Basic"},
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run-daily")
def run_daily(
    payload: RunDailyRequest = Body(default_factory=RunDailyRequest),
    _: str = Depends(_authenticate),
) -> dict[str, object]:
    if not run_daily_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="run_daily is already in progress.",
        )

    try:
        scrapers = instantiate_scrapers(payload.sites) if payload.sites else None
        pipeline = TrelloPipeline(scrapers=scrapers)
        result = pipeline.run(
            limit_per_site=payload.limit_per_site,
            dry_run=payload.dry_run,
            live_run=True,
        )
        return asdict(result)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    finally:
        run_daily_lock.release()
