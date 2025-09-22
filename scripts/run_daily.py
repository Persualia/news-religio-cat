"""Entry point for the scheduled daily ingestion job."""
import argparse
import json
import logging
import sys
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from logging_utils import setup_logging
from pipeline import DailyPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the daily news ingestion pipeline")
    parser.add_argument("--limit-per-site", type=int, default=None, help="Optional max articles per scraper")
    parser.add_argument("--dry-run", action="store_true", help="Scrape and log without indexing or external API calls")
    parser.add_argument("--no-index", action="store_true", help="Evita escribir en OpenSearch pero mantiene embeddings y resumen")
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
    pipeline = DailyPipeline()
    result = pipeline.run(
        limit_per_site=args.limit_per_site,
        dry_run=args.dry_run,
        skip_indexing=args.no_index,
    )
    print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
