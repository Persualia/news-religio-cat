"""Pipeline orchestrating scraping and Trello/Google Sheets integration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Optional, Sequence

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

import httpx
from integrations import GoogleSheetsRepository, SlackNotifier, TrelloClient
from models import NewsItem, SheetRecord, utcnow
from scraping import BaseScraper, SCRAPER_PRIORITY, instantiate_scrapers
from scraping.base import ScraperNoArticlesError

logger = logging.getLogger(__name__)

MAX_SHEET_ROWS = 800

if ZoneInfo:
    try:
        MADRID_TZ = ZoneInfo("Europe/Madrid")
    except Exception:  # pragma: no cover - tz data missing
        MADRID_TZ = timezone.utc
else:  # pragma: no cover
    MADRID_TZ = timezone.utc


@dataclass(slots=True)
class PipelineResult:
    sources_processed: int
    total_items: int
    new_items: int
    skipped_existing: int
    skipped_stale: int
    alerts_sent: int
    live: bool


class TrelloPipeline:
    """Coordinates scraping, deduplication and Trello card creation."""

    def __init__(
        self,
        *,
        scrapers: Optional[Sequence[BaseScraper]] = None,
        trello_client: Optional[TrelloClient] = None,
        sheets_repo: Optional[GoogleSheetsRepository] = None,
        slack_notifier: Optional[SlackNotifier] = None,
    ) -> None:
        self._scrapers = list(scrapers) if scrapers else instantiate_scrapers()
        self._trello = trello_client or TrelloClient()
        self._sheets = sheets_repo or GoogleSheetsRepository()
        self._slack = slack_notifier or SlackNotifier()

    def run(
        self,
        *,
        limit_per_site: Optional[int] = None,
        dry_run: bool = False,
        live_run: Optional[bool] = None,
    ) -> PipelineResult:
        live = _detect_live_run() if live_run is None else bool(live_run)
        logger.info(
            "==== TRENDING NEWS → TRELLO PIPELINE (dry_run=%s, live=%s) ====",
            dry_run,
            live,
        )

        existing_ids = self._sheets.fetch_existing_ids()
        logger.info("Loaded %d existing IDs from Google Sheets.", len(existing_ids))

        seen_ids = set(existing_ids)
        pending_items: list[NewsItem] = []
        records_to_append: list[SheetRecord] = []
        total_items = 0
        new_items = 0
        skipped_existing = 0
        skipped_stale = 0
        alerts_sent = 0
        stale_cutoff = utcnow() - timedelta(days=10)

        for scraper in self._scrapers:
            logger.info("Processing source: %s", scraper.site_id)
            try:
                items = scraper.scrape(limit=limit_per_site)
            except ScraperNoArticlesError as exc:
                alerts_sent += 1
                message = (
                    f":rotating_light: El scraper '{exc.site_id}' no retornó URLs. "
                    "Revisa posibles cambios en la web origen."
                )
                logger.warning(message)
                self._slack.notify(message)
                continue
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unexpected error scraping %s", scraper.site_id)
                alerts_sent += 1
                self._slack.notify(_format_scraper_error(scraper.site_id, exc))
                continue

            total_items += len(items)
            for item in items:
                if _is_stale(item, stale_cutoff):
                    skipped_stale += 1
                    logger.info(
                        "Skipping stale item (>10d): %s %s %s",
                        item.source,
                        item.published_at,
                        item.url,
                    )
                    continue

                if item.doc_id in seen_ids:
                    skipped_existing += 1
                    continue

                logger.info("New item detected: %s %s", item.source, item.url)
                seen_ids.add(item.doc_id)
                new_items += 1
                pending_items.append(item)

        ordered_items = sorted(pending_items, key=_item_sort_key)

        if not dry_run:
            for item in ordered_items:
                try:
                    card_id = self._trello.create_card(item)
                    logger.info("Created Trello card %s for %s", card_id or "<unknown>", item.url)
                except Exception:  # noqa: BLE001
                    alerts_sent += 1
                    self._slack.notify(
                        f":warning: Falló la creación de la tarjeta en Trello para {item.url}"
                    )
                    continue

                records_to_append.append(
                    SheetRecord(
                        date=_resolve_item_date(item),
                        doc_id=item.doc_id,
                        source=item.source,
                        title=item.title,
                        url=item.url,
                    )
                )

        if not dry_run and records_to_append:
            logger.info("Persisting %d new records to Google Sheets.", len(records_to_append))
            self._sheets.append_records(records_to_append)
            self._sheets.trim_to_limit(MAX_SHEET_ROWS)

        logger.info(
            "Pipeline completed: sources=%d, total=%d, new=%d, skipped=%d, alerts=%d",
            len(self._scrapers),
            total_items,
            new_items,
            skipped_existing,
            skipped_stale,
            alerts_sent,
        )

        result = PipelineResult(
            sources_processed=len(self._scrapers),
            total_items=total_items,
            new_items=new_items,
            skipped_existing=skipped_existing,
            skipped_stale=skipped_stale,
            alerts_sent=alerts_sent,
            live=live,
        )
        self._send_summary(result, dry_run=dry_run)
        return result

    def _send_summary(self, result: PipelineResult, *, dry_run: bool) -> None:
        notifier = getattr(self._slack, "notify_blocks", None)
        if not notifier:
            return

        blocks = _build_summary_blocks(result, dry_run)
        try:
            notifier(blocks=blocks, text="Resumen de la ingesta diaria completado.")
        except Exception:  # noqa: BLE001
            logger.debug("Unable to send Slack summary notification.", exc_info=True)


def _resolve_item_date(item: NewsItem) -> str:
    candidate = _resolve_item_datetime(item)
    return candidate.date().isoformat()


def _resolve_item_datetime(item: NewsItem) -> datetime:
    candidate: datetime | None = item.published_at or item.retrieved_at
    if candidate is None:
        candidate = utcnow()
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=timezone.utc)
    return candidate.astimezone(timezone.utc)


def _is_stale(item: NewsItem, cutoff: datetime) -> bool:
    """Return True when the item has a published_at older than the cutoff."""

    published = item.published_at
    if published is None:
        return False
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return published.astimezone(timezone.utc) < cutoff


def _item_sort_key(item: NewsItem) -> tuple[datetime, int, str, str]:
    timestamp = _resolve_item_datetime(item)
    source = item.source or ""
    priority = SCRAPER_PRIORITY.get(source, len(SCRAPER_PRIORITY))
    return (timestamp, -priority, source, item.url)


def _format_scraper_error(site_id: str, exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        status = response.status_code if response is not None else "unknown"
        reason = getattr(response, "reason_phrase", "") if response else ""
        url = str(response.request.url) if response and response.request else "<unknown>"
        return (
            f":warning: HTTP {status} {reason} al scrapear '{site_id}'. "
            f"URL: {url}"
        )
    return f":warning: Error inesperado al scrapear '{site_id}': {exc}"


def _detect_live_run() -> bool:
    for env_var in ("GITHUB_ACTIONS", "CI"):
        value = os.getenv(env_var, "")
        if value and value.lower() not in ("0", "false", "no"):
            return True
    return False


def _build_summary_blocks(result: PipelineResult, dry_run: bool) -> list[dict]:
    madrid_now = datetime.now(tz=MADRID_TZ)
    timestamp = madrid_now.strftime("%Y-%m-%d %H:%M:%S")

    fields = [
        ("Sources processed", result.sources_processed),
        ("Total items", result.total_items),
        ("New items", result.new_items),
        ("Skipped existing", result.skipped_existing),
        ("Skipped stale (>10d)", result.skipped_stale),
        ("Alerts sent", result.alerts_sent),
        ("Live", str(result.live).lower()),
    ]
    if dry_run:
        fields.append(("Mode", "dry-run"))

    field_blocks = [
        {"type": "mrkdwn", "text": f"*{label}*\n{value}"}
        for label, value in fields
    ]

    header_text = (
        "*Resumen de la ingesta diaria*"
        f"\n{timestamp} (Madrid)"
    )

    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": header_text},
        },
        {
            "type": "section",
            "fields": field_blocks,
        },
    ]


__all__ = ["TrelloPipeline", "PipelineResult"]
