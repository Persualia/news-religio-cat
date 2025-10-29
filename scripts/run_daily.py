"""Entry point for the Trello-based daily ingestion job."""
import argparse
import json
import logging
import sys
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dataclasses import asdict
from logging_utils import setup_logging
from pipeline import PipelineResult, TrelloPipeline
from scraping import instantiate_scrapers, list_scraper_ids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the news → Trello ingestion pipeline")
    parser.add_argument("--limit-per-site", type=int, default=None, help="Optional max items per scraper")
    parser.add_argument("--dry-run", action="store_true", help="Gather data without creating cards or writing sheets")
    parser.add_argument(
        "--sites",
        nargs="+",
        help=(
            "IDs de scrapers a ejecutar ("
            + ", ".join(list_scraper_ids())
            + ") separados por espacios o comas"
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(level=getattr(logging, args.log_level.upper()))

    site_ids: list[str] = []
    if args.sites:
        for fragment in args.sites:
            site_ids.extend(part.strip() for part in fragment.split(",") if part.strip())

    scrapers = None
    if site_ids:
        try:
            scrapers = instantiate_scrapers(site_ids)
        except ValueError as exc:
            logging.error("%s", exc)
            logging.error("Sitios disponibles: %s", ", ".join(list_scraper_ids()))
            sys.exit(1)

    pipeline = TrelloPipeline(scrapers=scrapers)
    result: PipelineResult = pipeline.run(limit_per_site=args.limit_per_site, dry_run=args.dry_run)
    print(json.dumps(asdict(result), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
