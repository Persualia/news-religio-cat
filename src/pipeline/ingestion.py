"""Pipeline orchestrating scraping and Trello/Google Sheets integration."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Optional, Sequence

from integrations import GoogleSheetsRepository, SlackNotifier, TrelloClient
from models import NewsItem, SheetRecord, utcnow
from scraping import BaseScraper, instantiate_scrapers
from scraping.base import ScraperNoArticlesError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PipelineResult:
    sources_processed: int
    total_items: int
    new_items: int
    skipped_existing: int
    alerts_sent: int
    dry_run: bool


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
    ) -> PipelineResult:
        logger.info("==== TRENDING NEWS → TRELLO PIPELINE (dry_run=%s) ====", dry_run)

        existing_ids = self._sheets.fetch_existing_ids()
        logger.info("Loaded %d existing IDs from Google Sheets.", len(existing_ids))

        seen_ids = set(existing_ids)
        records_to_append: list[SheetRecord] = []
        total_items = 0
        new_items = 0
        skipped_existing = 0
        alerts_sent = 0
        ingest_date = utcnow().date().isoformat()

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
            except Exception:  # noqa: BLE001
                logger.exception("Unexpected error scraping %s", scraper.site_id)
                alerts_sent += 1
                self._slack.notify(
                    f":warning: Error inesperado al scrapear '{scraper.site_id}'. Revisa los logs."
                )
                continue

            total_items += len(items)
            for item in items:
                if item.doc_id in seen_ids:
                    skipped_existing += 1
                    continue

                logger.info("New item detected: %s %s", item.source, item.url)
                seen_ids.add(item.doc_id)
                new_items += 1

                if dry_run:
                    continue

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
                        date=ingest_date,
                        doc_id=item.doc_id,
                        source=item.source,
                        title=item.title,
                    )
                )

        if not dry_run and records_to_append:
            logger.info("Persisting %d new records to Google Sheets.", len(records_to_append))
            self._sheets.append_records(records_to_append)

        logger.info(
            "Pipeline completed: sources=%d, total=%d, new=%d, skipped=%d, alerts=%d",
            len(self._scrapers),
            total_items,
            new_items,
            skipped_existing,
            alerts_sent,
        )

        return PipelineResult(
            sources_processed=len(self._scrapers),
            total_items=total_items,
            new_items=new_items,
            skipped_existing=skipped_existing,
            alerts_sent=alerts_sent,
            dry_run=dry_run,
        )


__all__ = ["TrelloPipeline", "PipelineResult"]
