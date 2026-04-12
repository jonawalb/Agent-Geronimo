"""Base scraper class for all discovery sources."""
import logging
from abc import ABC, abstractmethod
from typing import List

from ..models import Opportunity, SourceResult
from ..utils.http_client import RateLimitedClient
from ..utils.cache import Cache

logger = logging.getLogger("geronimo.discovery")


class BaseScraper(ABC):
    """Abstract base class for all funding source scrapers."""

    source_name: str = "unknown"

    def __init__(self, client: RateLimitedClient, cache: Cache, keywords: dict):
        self.client = client
        self.cache = cache
        self.keywords = keywords

    @abstractmethod
    def search(self, queries: List[str]) -> SourceResult:
        """Execute search queries and return opportunities."""
        pass

    def _make_opportunity(self, **kwargs) -> Opportunity:
        """Create an Opportunity with source metadata pre-filled."""
        from datetime import datetime
        opp = Opportunity(
            source_name=self.source_name,
            scrape_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
            **kwargs,
        )
        opp.generate_dedup_key()
        return opp
