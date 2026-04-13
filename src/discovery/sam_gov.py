"""SAM.gov Contract Opportunities API scraper.

SAM.gov provides federal contract opportunities (formerly FBO.gov).
API docs: https://open.gsa.gov/api/get-opportunities-public-api/
Requires free API key from api.sam.gov

Enhanced to:
- Search multiple pages (pagination)
- Filter out already-awarded and closed opportunities
- Include forecasted and presolicitation opportunities
- Search by specific agencies (DOD, DARPA, DTRA, services, ONA, etc.)
"""
import logging
import os
import re
from datetime import datetime, date
from typing import List, Optional

from .base import BaseScraper
from ..models import Opportunity, SourceResult

logger = logging.getLogger("geronimo.discovery.sam_gov")

SEARCH_URL = "https://api.sam.gov/prod/opportunities/v2/search"

# Agency-specific NAICS codes relevant to security/defense research
RELEVANT_NAICS = [
    "541611",  # Administrative Management Consulting
    "541612",  # Human Resources Consulting
    "541618",  # Other Management Consulting
    "541690",  # Other Scientific and Technical Consulting
    "541715",  # R&D in Physical, Engineering, and Life Sciences
    "541720",  # Research and Development in Social Sciences
    "611310",  # Colleges/Universities
    "611710",  # Educational Support Services
]

# Statuses that indicate the opportunity is NOT available to apply for
EXCLUDED_AWARD_STATUSES = {
    "award notice",
    "awarded",
    "closed",
    "canceled",
    "cancelled",
    "archived",
    "suspended",
    "deleted",
}

# Statuses/types that indicate the opportunity IS available or upcoming
INCLUDED_STATUSES = {
    "active",
    "forecasted",
    "presolicitation",
    "posted",
    "open",
}


class SamGovScraper(BaseScraper):
    """Scraper for SAM.gov contract opportunities."""

    source_name = "SAM.gov"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = os.environ.get("SAM_GOV_API_KEY", "DEMO_KEY")

    def search(self, queries: List[str]) -> SourceResult:
        """Search SAM.gov for contract opportunities across keywords and agencies."""
        result = SourceResult(source_name=self.source_name)
        seen_ids = set()

        # Phase 1: Keyword-based searches
        for query in queries:
            result.query_count += 1
            try:
                opps = self._search_query(query, seen_ids)
                result.opportunities.extend(opps)
                result.result_count += len(opps)
            except Exception as e:
                logger.warning(f"SAM.gov query '{query}' failed: {e}")
                result.errors.append(f"Query '{query}': {e}")

        # Phase 2: Agency-specific searches to catch opportunities
        # that keyword searches might miss
        agency_queries = self._build_agency_queries()
        for agency_name, agency_params in agency_queries:
            result.query_count += 1
            try:
                opps = self._search_by_agency(agency_name, agency_params, seen_ids)
                result.opportunities.extend(opps)
                result.result_count += len(opps)
            except Exception as e:
                logger.warning(f"SAM.gov agency '{agency_name}' failed: {e}")
                result.errors.append(f"Agency '{agency_name}': {e}")

        # Phase 3: Notice-type-specific searches (BAAs, RFIs, presolicitations)
        notice_types = [
            ("p", "Presolicitation"),
            ("r", "Sources Sought"),
            ("k", "Combined Synopsis/Solicitation"),
            ("o", "Solicitation"),
        ]
        for ntype, ntype_label in notice_types:
            result.query_count += 1
            try:
                opps = self._search_by_notice_type(ntype, ntype_label, seen_ids)
                result.opportunities.extend(opps)
                result.result_count += len(opps)
            except Exception as e:
                logger.warning(f"SAM.gov notice type '{ntype_label}' failed: {e}")
                result.errors.append(f"Notice type '{ntype_label}': {e}")

        logger.info(
            f"SAM.gov: {result.result_count} opportunities from "
            f"{result.query_count} queries"
        )
        return result

    def _build_agency_queries(self) -> List[tuple]:
        """Build agency-specific search parameters."""
        agencies = [
            ("DARPA", {"departmentname": "DEPT OF DEFENSE", "subtier": "Defense Advanced Research Projects Agency"}),
            ("DTRA", {"departmentname": "DEPT OF DEFENSE", "subtier": "Defense Threat Reduction Agency"}),
            ("Navy/ONR", {"departmentname": "DEPT OF DEFENSE", "subtier": "DEPT OF THE NAVY"}),
            ("Army/ARO", {"departmentname": "DEPT OF DEFENSE", "subtier": "DEPT OF THE ARMY"}),
            ("Air Force/AFOSR", {"departmentname": "DEPT OF DEFENSE", "subtier": "DEPT OF THE AIR FORCE"}),
            ("OSD/Net Assessment", {"departmentname": "DEPT OF DEFENSE", "subtier": "Office of the Secretary of Defense"}),
            ("DHS S&T", {"departmentname": "DEPT OF HOMELAND SECURITY", "subtier": "Science and Technology Directorate"}),
            ("State/DRL", {"departmentname": "STATE, DEPARTMENT OF"}),
            ("IARPA", {"departmentname": "OTHER DOD AND DEFENSE AGENCIES", "subtier": "Intelligence Advanced Research Projects Activity"}),
            ("NSF", {"departmentname": "NATIONAL SCIENCE FOUNDATION"}),
            ("DOE", {"departmentname": "ENERGY, DEPARTMENT OF"}),
            ("Marine Corps", {"departmentname": "DEPT OF DEFENSE", "subtier": "UNITED STATES MARINE CORPS"}),
            ("SOCOM", {"departmentname": "DEPT OF DEFENSE", "subtier": "U.S. Special Operations Command"}),
            ("DIU", {"departmentname": "DEPT OF DEFENSE", "subtier": "Defense Innovation Unit"}),
            ("USAID", {"departmentname": "AGENCY FOR INTERNATIONAL DEVELOPMENT"}),
        ]
        return agencies

    def _search_query(self, keyword: str, seen_ids: set) -> List[Opportunity]:
        """Execute a single keyword search with pagination."""
        all_opportunities = []
        offset = 0
        max_pages = 3  # Up to 300 results per keyword

        while offset < max_pages * 100:
            cache_key = f"{keyword}_offset{offset}"
            cached = self.cache.get(SEARCH_URL, {"keyword": cache_key})
            if cached:
                page_opps = self._parse_results(cached, seen_ids)
                all_opportunities.extend(page_opps)
                if len(page_opps) < 100:
                    break
                offset += 100
                continue

            params = {
                "api_key": self.api_key,
                "q": keyword,
                "postedFrom": "01/01/2024",
                "limit": 100,
                "offset": offset,
                "ptype": "o,p,k,r",  # solicitation, presolicitation, combined, sources sought
            }

            resp = self.client.get(SEARCH_URL, params=params)
            if resp:
                try:
                    data = resp.json()
                    self.cache.set(SEARCH_URL, data, params={"keyword": cache_key},
                                  source=self.source_name)
                    page_opps = self._parse_results(data, seen_ids)
                    all_opportunities.extend(page_opps)
                    if len(page_opps) < 100:
                        break
                except Exception as e:
                    logger.warning(f"Failed to parse SAM.gov response for '{keyword}' offset {offset}: {e}")
                    break
            else:
                break

            offset += 100

        return all_opportunities

    def _search_by_agency(self, agency_name: str, agency_params: dict, seen_ids: set) -> List[Opportunity]:
        """Search SAM.gov filtered by agency/department."""
        cache_key = f"agency_{agency_name}"
        cached = self.cache.get(SEARCH_URL, {"keyword": cache_key})
        if cached:
            return self._parse_results(cached, seen_ids)

        params = {
            "api_key": self.api_key,
            "postedFrom": "01/01/2024",
            "limit": 100,
            "offset": 0,
            "ptype": "o,p,k,r",
        }
        params.update(agency_params)

        resp = self.client.get(SEARCH_URL, params=params)
        if resp:
            try:
                data = resp.json()
                self.cache.set(SEARCH_URL, data, params={"keyword": cache_key},
                              source=self.source_name)
                return self._parse_results(data, seen_ids)
            except Exception as e:
                logger.warning(f"Failed to parse SAM.gov agency response for '{agency_name}': {e}")

        return []

    def _search_by_notice_type(self, ntype: str, label: str, seen_ids: set) -> List[Opportunity]:
        """Search by specific notice type for broader coverage."""
        cache_key = f"ntype_{ntype}"
        cached = self.cache.get(SEARCH_URL, {"keyword": cache_key})
        if cached:
            return self._parse_results(cached, seen_ids)

        # Use defense/security keywords with specific notice type
        security_keywords = [
            "security", "defense", "intelligence", "strategic",
            "Indo-Pacific", "deterrence", "information operations",
        ]
        all_opps = []

        for kw in security_keywords[:3]:  # Limit to avoid rate limiting
            params = {
                "api_key": self.api_key,
                "q": kw,
                "postedFrom": "01/01/2024",
                "limit": 100,
                "offset": 0,
                "ptype": ntype,
            }

            resp = self.client.get(SEARCH_URL, params=params)
            if resp:
                try:
                    data = resp.json()
                    opps = self._parse_results(data, seen_ids)
                    all_opps.extend(opps)
                except Exception as e:
                    logger.warning(f"SAM.gov notice type search '{label}/{kw}' failed: {e}")

        return all_opps

    def _parse_results(self, data: dict, seen_ids: set) -> List[Opportunity]:
        """Parse SAM.gov API response, filtering out awarded/closed opportunities."""
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

            title = hit.get("title", "")
            if not title:
                continue

            # --- Filter out awarded/closed/archived opportunities ---
            if self._is_excluded(hit, title):
                continue

            seen_ids.add(notice_id)

            # Determine opportunity type from notice type
            notice_type = hit.get("type", hit.get("noticeType", "")).lower()
            opp_type = self._classify_type(notice_type, title)

            # Determine status for metadata
            status = self._extract_status(hit)

            sol_number = hit.get("solicitationNumber", "")
            department = hit.get("department", hit.get("departmentName", ""))
            sub_agency = hit.get("subtierAgency", hit.get("office", ""))

            deadline = hit.get("responseDeadLine", hit.get("archiveDate", ""))
            open_date = hit.get("postedDate", "")

            opp = self._make_opportunity(
                opportunity_id=notice_id,
                title=title,
                opportunity_type=opp_type,
                funder=department,
                sub_agency=sub_agency,
                source_website="https://sam.gov",
                listing_url=f"https://sam.gov/opp/{notice_id}/view" if notice_id else "",
                application_url=hit.get("uiLink", ""),
                synopsis=hit.get("description", hit.get("synopsis", "")),
                deadline=deadline,
                open_date=open_date,
                award_min=str(hit.get("award", {}).get("floor", "")) if isinstance(hit.get("award"), dict) else "",
                award_max=str(hit.get("award", {}).get("ceiling", "")) if isinstance(hit.get("award"), dict) else "",
                topic_area=hit.get("naicsCode", ""),
                eligibility_text=hit.get("setAside", ""),
                notes=f"Status: {status}" if status else "",
            )
            opportunities.append(opp)

        return opportunities

    def _is_excluded(self, hit: dict, title: str) -> bool:
        """Check if an opportunity should be excluded (awarded, closed, etc.)."""
        # Check notice type for award notices
        notice_type = hit.get("type", hit.get("noticeType", "")).lower()
        if any(excl in notice_type for excl in EXCLUDED_AWARD_STATUSES):
            return True

        # Check active status field
        active = hit.get("active", hit.get("isActive", ""))
        if isinstance(active, str) and active.lower() in ("no", "false", "inactive"):
            return True
        if isinstance(active, bool) and not active:
            return True

        # Check archive type / status
        archive_type = hit.get("archiveType", "").lower()
        if archive_type in ("manual", "auto") and not hit.get("responseDeadLine"):
            return True

        # Check if deadline has passed (and it's not a forecasted/upcoming one)
        deadline = hit.get("responseDeadLine", "")
        if deadline and not self._is_forecasted(hit):
            if self._is_past_deadline(deadline):
                return True

        # Check title patterns that indicate already-awarded
        title_lower = title.lower()
        award_patterns = [
            "award notice",
            "intent to sole source",
            "justification and approval",
            "j&a -",
            "j&a-",
            "modification ",
        ]
        if any(pat in title_lower for pat in award_patterns):
            # Exception: if it mentions "funding available" or "subcontracting"
            if any(keep in title_lower for keep in ["funding available", "subcontract", "teaming"]):
                return False
            return True

        return False

    def _is_forecasted(self, hit: dict) -> bool:
        """Check if the opportunity is forecasted / upcoming."""
        notice_type = hit.get("type", hit.get("noticeType", "")).lower()
        return "presol" in notice_type or "forecast" in notice_type

    def _is_past_deadline(self, deadline_str: str) -> bool:
        """Check if a deadline string represents a past date."""
        today = date.today()
        for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y",
                    "%m-%d-%Y", "%d %B %Y", "%m/%d/%y",
                    "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y %H:%M"]:
            try:
                dl = datetime.strptime(deadline_str.strip(), fmt).date()
                return dl < today
            except ValueError:
                continue
        return False

    def _extract_status(self, hit: dict) -> str:
        """Extract a human-readable status string."""
        notice_type = hit.get("type", hit.get("noticeType", "")).lower()
        if "presol" in notice_type:
            return "Presolicitation (upcoming)"
        if "forecast" in notice_type:
            return "Forecasted"
        if "sources" in notice_type:
            return "Sources Sought"
        if "combined" in notice_type:
            return "Combined Synopsis/Solicitation"
        if "solicitation" in notice_type:
            return "Solicitation (open)"
        active = hit.get("active", "")
        if str(active).lower() in ("yes", "true"):
            return "Active"
        return ""

    def _classify_type(self, notice_type: str, title: str) -> str:
        """Classify opportunity type from notice type and title."""
        title_lower = title.lower()

        if "presol" in notice_type:
            return "Presolicitation"
        if "forecast" in notice_type:
            return "Forecasted"
        if "sources" in notice_type:
            return "RFI"
        if "baa" in title_lower or "broad agency announcement" in title_lower:
            return "BAA"
        if "rfp" in notice_type or "rfp" in title_lower or "request for proposal" in title_lower:
            return "RFP"
        if "rfi" in title_lower or "request for information" in title_lower:
            return "RFI"
        if "cooperative agreement" in title_lower:
            return "Cooperative Agreement"
        if "combined" in notice_type:
            return "BAA"
        return "Contract"
