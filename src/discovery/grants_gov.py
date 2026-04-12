"""Grants.gov API scraper.

Grants.gov provides a public REST API for searching federal grant opportunities.
Docs: https://api.grants.gov/
No API key required for basic search, but rate-limited.
"""
import logging
import time
from typing import List

from .base import BaseScraper
from ..models import Opportunity, SourceResult

logger = logging.getLogger("geronimo.discovery.grants_gov")

# Grants.gov REST API endpoints (apply07 is the working public endpoint)
SEARCH_URL = "https://apply07.grants.gov/grantsws/rest/opportunities/search"
DETAIL_URL = "https://apply07.grants.gov/grantsws/rest/opportunity/details"


class GrantsGovScraper(BaseScraper):
    """Scraper for Grants.gov federal grant opportunities."""

    source_name = "Grants.gov"

    def search(self, queries: List[str]) -> SourceResult:
        """Search Grants.gov for each query keyword."""
        result = SourceResult(source_name=self.source_name)
        seen_ids = set()

        for query in queries:
            result.query_count += 1
            try:
                opps = self._search_query(query, seen_ids)
                result.opportunities.extend(opps)
                result.result_count += len(opps)
            except Exception as e:
                logger.warning(f"Grants.gov query '{query}' failed: {e}")
                result.errors.append(f"Query '{query}': {e}")

        logger.info(
            f"Grants.gov: {result.result_count} opportunities from "
            f"{result.query_count} queries"
        )
        return result

    def _search_query(self, keyword: str, seen_ids: set) -> List[Opportunity]:
        """Execute a single search query against Grants.gov API."""
        opportunities = []

        # Check cache first
        cached = self.cache.get(SEARCH_URL, {"keyword": keyword})
        if cached:
            return self._parse_results(cached, seen_ids)

        # Grants.gov apply07 API uses POST with JSON body
        payload = {
            "keyword": keyword,
            "oppStatuses": "posted|forecasted",
            "rows": 100,
            "sortBy": "openDate|desc",
        }

        resp = self.client.post(
            SEARCH_URL, json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        if resp:
            try:
                data = resp.json()
                self.cache.set(SEARCH_URL, data, params={"keyword": keyword},
                              source=self.source_name)
                opportunities = self._parse_results(data, seen_ids)
            except Exception as e:
                logger.warning(f"Failed to parse Grants.gov response for '{keyword}': {e}")

        return opportunities

    def _parse_results(self, data: dict, seen_ids: set) -> List[Opportunity]:
        """Parse Grants.gov API response into Opportunity objects."""
        opportunities = []

        # Handle different response formats
        hits = []
        if isinstance(data, dict):
            hits = data.get("oppHits", [])
            if not hits:
                hits = data.get("opportunities", [])
            if not hits and "data" in data:
                hits = data["data"] if isinstance(data["data"], list) else []

        for hit in hits:
            opp_id = str(hit.get("id", hit.get("opportunityId", hit.get("oppNumber", ""))))
            if not opp_id or opp_id in seen_ids:
                continue
            seen_ids.add(opp_id)

            title = hit.get("title", hit.get("oppTitle", ""))
            if not title:
                continue

            opp = self._make_opportunity(
                opportunity_id=opp_id,
                title=title,
                opportunity_type="Grant",
                funder=hit.get("agency", hit.get("agencyName", "Federal")),
                sub_agency=hit.get("subAgency", hit.get("subAgencyName", "")),
                source_website="https://www.grants.gov",
                listing_url=f"https://www.grants.gov/search-results-detail/{opp_id}",
                application_url=hit.get("applicationUrl", f"https://www.grants.gov/search-results-detail/{opp_id}"),
                synopsis=hit.get("synopsis", hit.get("description", "")),
                deadline=hit.get("closeDate", hit.get("closingDate", "")),
                open_date=hit.get("openDate", hit.get("openingDate", "")),
                award_min=str(hit.get("awardFloor", "")) if hit.get("awardFloor") else "",
                award_max=str(hit.get("awardCeiling", "")) if hit.get("awardCeiling") else "",
                typical_award=str(hit.get("estimatedFunding", "")) if hit.get("estimatedFunding") else "",
                num_awards_expected=str(hit.get("expectedNumberOfAwards", "")),
                cost_share=hit.get("costSharing", ""),
                eligibility_text=hit.get("eligibleApplicants", ""),
                topic_area=hit.get("cfda", hit.get("cfdaNumber", "")),
            )
            opportunities.append(opp)

        return opportunities

    def get_detail(self, opp_id: str) -> dict:
        """Fetch detailed information for a specific opportunity."""
        cache_key = f"grants_gov_detail_{opp_id}"
        cached = self.cache.get(DETAIL_URL, {"id": opp_id})
        if cached:
            return cached

        resp = self.client.get(f"{DETAIL_URL}/{opp_id}")
        if resp:
            try:
                data = resp.json()
                self.cache.set(DETAIL_URL, data, params={"id": opp_id},
                              source=self.source_name)
                return data
            except Exception:
                pass
        return {}
