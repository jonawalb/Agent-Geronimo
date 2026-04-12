"""SAM.gov Contract Opportunities API scraper.

SAM.gov provides federal contract opportunities (formerly FBO.gov).
API docs: https://open.gsa.gov/api/get-opportunities-public-api/
Requires free API key from api.sam.gov
"""
import logging
import os
from typing import List

from .base import BaseScraper
from ..models import Opportunity, SourceResult

logger = logging.getLogger("geronimo.discovery.sam_gov")

SEARCH_URL = "https://api.sam.gov/prod/opportunities/v2/search"


class SamGovScraper(BaseScraper):
    """Scraper for SAM.gov contract opportunities."""

    source_name = "SAM.gov"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = os.environ.get("SAM_GOV_API_KEY", "DEMO_KEY")

    def search(self, queries: List[str]) -> SourceResult:
        """Search SAM.gov for contract opportunities."""
        result = SourceResult(source_name=self.source_name)
        seen_ids = set()

        for query in queries:
            result.query_count += 1
            try:
                opps = self._search_query(query, seen_ids)
                result.opportunities.extend(opps)
                result.result_count += len(opps)
            except Exception as e:
                logger.warning(f"SAM.gov query '{query}' failed: {e}")
                result.errors.append(f"Query '{query}': {e}")

        logger.info(
            f"SAM.gov: {result.result_count} opportunities from "
            f"{result.query_count} queries"
        )
        return result

    def _search_query(self, keyword: str, seen_ids: set) -> List[Opportunity]:
        """Execute a single search query against SAM.gov API."""
        opportunities = []

        cached = self.cache.get(SEARCH_URL, {"keyword": keyword})
        if cached:
            return self._parse_results(cached, seen_ids)

        params = {
            "api_key": self.api_key,
            "q": keyword,
            "postedFrom": "01/01/2025",
            "limit": 100,
            "offset": 0,
            "ptype": "o,p,k",  # o=solicitation, p=presolicitation, k=combined
            "status": "active",
        }

        resp = self.client.get(SEARCH_URL, params=params)
        if resp:
            try:
                data = resp.json()
                self.cache.set(SEARCH_URL, data, params={"keyword": keyword},
                              source=self.source_name)
                opportunities = self._parse_results(data, seen_ids)
            except Exception as e:
                logger.warning(f"Failed to parse SAM.gov response for '{keyword}': {e}")

        return opportunities

    def _parse_results(self, data: dict, seen_ids: set) -> List[Opportunity]:
        """Parse SAM.gov API response into Opportunity objects."""
        opportunities = []

        hits = []
        if isinstance(data, dict):
            hits = data.get("opportunitiesData", [])
            if not hits:
                hits = data.get("_embedded", {}).get("results", [])
            if not hits and "data" in data:
                hits = data.get("data", [])

        for hit in hits:
            notice_id = str(hit.get("noticeId", hit.get("solicitationNumber", "")))
            if not notice_id or notice_id in seen_ids:
                continue
            seen_ids.add(notice_id)

            title = hit.get("title", "")
            if not title:
                continue

            # Determine opportunity type from notice type
            notice_type = hit.get("type", hit.get("noticeType", "")).lower()
            opp_type = "Contract"
            if "presol" in notice_type:
                opp_type = "RFI"
            elif "combined" in notice_type or "baa" in title.lower():
                opp_type = "BAA"
            elif "rfp" in notice_type or "rfp" in title.lower():
                opp_type = "RFP"
            elif "sources" in notice_type:
                opp_type = "RFI"

            sol_number = hit.get("solicitationNumber", "")
            opp = self._make_opportunity(
                opportunity_id=notice_id,
                title=title,
                opportunity_type=opp_type,
                funder=hit.get("department", hit.get("departmentName", "")),
                sub_agency=hit.get("subtierAgency", hit.get("office", "")),
                source_website="https://sam.gov",
                listing_url=f"https://sam.gov/opp/{notice_id}/view" if notice_id else "",
                application_url=hit.get("uiLink", ""),
                synopsis=hit.get("description", hit.get("synopsis", "")),
                deadline=hit.get("responseDeadLine", hit.get("archiveDate", "")),
                open_date=hit.get("postedDate", ""),
                award_min=str(hit.get("award", {}).get("floor", "")) if isinstance(hit.get("award"), dict) else "",
                award_max=str(hit.get("award", {}).get("ceiling", "")) if isinstance(hit.get("award"), dict) else "",
                topic_area=hit.get("naicsCode", ""),
                eligibility_text=hit.get("setAside", ""),
            )
            opportunities.append(opp)

        return opportunities
