"""Scraper implementations for news ingestion."""
from .base import BaseScraper
from .salesians import SalesiansScraper

__all__ = ["BaseScraper", "SalesiansScraper"]
