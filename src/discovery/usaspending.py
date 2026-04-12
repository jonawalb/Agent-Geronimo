"""USAspending.gov API client for past award intelligence.

Public API, no key needed. Used to gather funder intelligence
by analyzing previously funded projects.
Docs: https://api.usaspending.gov/
"""
import logging
from typing import List, Dict

from .base import BaseScraper
from ..models import SourceResult

logger = logging.getLogger("geronimo.discovery.usaspending")

BASE_URL = "https://api.usaspending.gov/api/v2"


class USASpendingScraper(BaseScraper):
    """Client for USAspending.gov past award data."""

    source_name = "USAspending.gov"

    def search(self, queries: List[str]) -> SourceResult:
        """Search past awards for funder intelligence."""
        result = SourceResult(source_name=self.source_name)

        for query in queries[:10]:  # Limit queries for past-award analysis
            result.query_count += 1
            try:
                awards = self._search_awards(query)
                result.result_count += len(awards)
                # Store as metadata, not as new opportunities
                for award in awards:
                    self.cache.store_opportunity(
                        f"usaspending_{award.get('id', '')}",
                        award,
                        source=self.source_name,
                    )
            except Exception as e:
                logger.warning(f"USAspending query '{query}' failed: {e}")
                result.errors.append(str(e))

        return result

    def _search_awards(self, keyword: str) -> List[Dict]:
        """Search for past awards matching keyword."""
        cached = self.cache.get(f"{BASE_URL}/search/spending_by_award", {"keyword": keyword})
        if cached:
            return cached.get("results", [])

        payload = {
            "filters": {
                "keywords": [keyword],
                "time_period": [
                    {"start_date": "2020-01-01", "end_date": "2026-12-31"}
                ],
            },
            "fields": [
                "Award ID", "Recipient Name", "Description",
                "Award Amount", "Awarding Agency", "Awarding Sub Agency",
                "Start Date", "End Date", "Award Type",
            ],
            "limit": 50,
            "page": 1,
            "sort": "Award Amount",
            "order": "desc",
        }

        resp = self.client.post(
            f"{BASE_URL}/search/spending_by_award",
            json=payload,
        )
        if resp:
            try:
                data = resp.json()
                self.cache.set(
                    f"{BASE_URL}/search/spending_by_award",
                    data,
                    params={"keyword": keyword},
                    source=self.source_name,
                )
                return data.get("results", [])
            except Exception as e:
                logger.warning(f"USAspending parse error: {e}")
        return []

    def get_agency_profile(self, agency_name: str) -> Dict:
        """Get award profile for a specific agency."""
        resp = self.client.post(
            f"{BASE_URL}/search/spending_by_award",
            json={
                "filters": {
                    "agencies": [{"type": "awarding", "tier": "toptier", "name": agency_name}],
                    "time_period": [{"start_date": "2022-01-01", "end_date": "2026-12-31"}],
                    "keywords": [
                        "security", "defense", "intelligence", "policy",
                        "strategic", "cyber", "resilience",
                    ],
                },
                "fields": [
                    "Award ID", "Recipient Name", "Description",
                    "Award Amount", "Start Date", "Award Type",
                ],
                "limit": 25,
                "sort": "Award Amount",
                "order": "desc",
            },
        )
        if resp:
            try:
                return resp.json()
            except Exception:
                pass
        return {}
