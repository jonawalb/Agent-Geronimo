"""Web search-based discovery for sources without APIs.

Uses targeted Google searches and direct website scraping to find
opportunities from foundations, agencies, think tanks, congressional
commissions, and other sources that don't provide structured APIs.

Enhanced to:
- Add US-Japan Foundation, congressional commissions, APL
- Improve think tank scraping to find actual open grants
- Add more government agency direct scraping
- Better filtering of non-grant links
"""
import logging
import re
import os
from typing import List, Optional
from urllib.parse import urljoin, urlparse
from datetime import datetime, date

from bs4 import BeautifulSoup

from .base import BaseScraper
from ..models import Opportunity, SourceResult

logger = logging.getLogger("geronimo.discovery.web_search")

# Words that indicate an actual funding opportunity vs. a general page
GRANT_SIGNAL_WORDS = re.compile(
    r'(grant|fund|fellowship|call for|proposal|solicitation|opportunity|'
    r'apply|application|rfp|baa|nofo|announcement|program|award|'
    r'request for|letter of inquiry|LOI|concept paper|white paper|'
    r'deadline|submit|open now|accepting|competition|prize|'
    r'cooperative agreement|assistance listing)',
    re.IGNORECASE,
)

# Words that indicate the link is NOT an actual grant opportunity
NON_GRANT_PATTERNS = re.compile(
    r'(about us|contact|staff|board|history|mission|vision|press release|'
    r'news|blog|event|conference|webinar|podcast|subscribe|donate|'
    r'annual report|privacy|terms of|login|sign in|careers|jobs|'
    r'publications|library|media kit|newsletter)',
    re.IGNORECASE,
)

# Closed/past indicators
CLOSED_PATTERNS = re.compile(
    r'(closed|expired|past|archived|completed|no longer|deadline passed|'
    r'applications? closed|window closed|cycle ended)',
    re.IGNORECASE,
)


class WebSearchScraper(BaseScraper):
    """Discovery via web search and targeted site scraping."""

    source_name = "Web Search"

    def search(self, queries: List[str]) -> SourceResult:
        """Run targeted web searches for funding opportunities."""
        result = SourceResult(source_name=self.source_name)

        # --- Government agencies with direct funding pages ---
        gov_sites = self._get_government_sites()
        for site_name, url in gov_sites:
            result.query_count += 1
            try:
                opps = self._scrape_site(site_name, url)
                result.opportunities.extend(opps)
                result.result_count += len(opps)
            except Exception as e:
                logger.warning(f"Failed to scrape {site_name}: {e}")
                result.errors.append(f"{site_name}: {e}")

        # --- Foundations with actual grant programs ---
        foundation_sites = self._get_foundation_sites()
        for site_name, url in foundation_sites:
            result.query_count += 1
            try:
                opps = self._scrape_site(site_name, url)
                result.opportunities.extend(opps)
                result.result_count += len(opps)
            except Exception as e:
                logger.warning(f"Failed to scrape {site_name}: {e}")
                result.errors.append(f"{site_name}: {e}")

        # --- Think tanks (scrape for actual open grants/fellowships) ---
        think_tank_sites = self._get_think_tank_grant_pages()
        for site_name, url in think_tank_sites:
            result.query_count += 1
            try:
                opps = self._scrape_site(site_name, url)
                result.opportunities.extend(opps)
                result.result_count += len(opps)
            except Exception as e:
                logger.warning(f"Failed to scrape {site_name}: {e}")
                result.errors.append(f"{site_name}: {e}")

        # --- Congressional commissions and committees ---
        congress_sites = self._get_congressional_sites()
        for site_name, url in congress_sites:
            result.query_count += 1
            try:
                opps = self._scrape_site(site_name, url)
                result.opportunities.extend(opps)
                result.result_count += len(opps)
            except Exception as e:
                logger.warning(f"Failed to scrape {site_name}: {e}")
                result.errors.append(f"{site_name}: {e}")

        # --- Keyword-driven web searches ---
        search_queries = self._build_search_queries(queries[:15])
        for sq in search_queries:
            result.query_count += 1
            try:
                opps = self._google_search(sq)
                result.opportunities.extend(opps)
                result.result_count += len(opps)
            except Exception as e:
                result.errors.append(f"Search '{sq}': {e}")

        logger.info(f"Web Search: {result.result_count} from {result.query_count} queries")
        return result

    def _get_government_sites(self) -> List[tuple]:
        """Government agencies with direct funding/opportunity pages."""
        return [
            ("DARPA Opportunities", "https://www.darpa.mil/work-with-us/opportunities"),
            ("DARPA BAAs", "https://sam.gov/search/?index=opp&sort=-modifiedDate&page=1&pageSize=25&sfm%5Bstatus%5D%5Bis_active%5D=true&sfm%5BsimpleSearch%5D%5BkeywordTags%5D%5B0%5D%5Bkey%5D=DARPA"),
            ("DIU Work With Us", "https://www.diu.mil/work-with-us"),
            ("Minerva Research Initiative", "https://minerva.defense.gov/Research/Funding-Opportunities/"),
            ("Minerva Topics", "https://minerva.defense.gov/"),
            ("Challenge.gov", "https://www.challenge.gov/?state=open"),
            ("NED Grants", "https://www.ned.org/apply-for-grant/en/"),
            ("State Dept DRL", "https://www.state.gov/bureau-of-democracy-human-rights-and-labor/"),
            ("State Dept INR", "https://www.state.gov/bureaus-offices/under-secretary-for-political-affairs/bureau-of-intelligence-and-research/"),
            ("DHS S&T Funding", "https://www.dhs.gov/science-and-technology/grants-and-funding"),
            ("IARPA Programs", "https://www.iarpa.gov/research-programs"),
            ("ONR Funding", "https://www.nre.navy.mil/work-with-us/funding-opportunities"),
            ("ARO Opportunities", "https://www.arl.army.mil/opportunities/"),
            ("AFOSR", "https://www.afrl.af.mil/AFRLHorizons/AFOSR/"),
            ("DTRA Opportunities", "https://www.dtra.mil/Opportunities/"),
            ("NSF Security-Related", "https://www.nsf.gov/funding/"),
            ("SBIR Open", "https://www.sbir.gov/solicitations/open"),
            ("APL Partnerships", "https://www.jhuapl.edu/work-with-us"),
            ("RAND Funding", "https://www.rand.org/about/contribute.html"),
            ("USAID Funding", "https://www.usaid.gov/work-usaid/find-a-funding-opportunity"),
        ]

    def _get_foundation_sites(self) -> List[tuple]:
        """Foundations with actual open grant programs."""
        return [
            ("Smith Richardson Foundation", "https://www.srf.org/programs/international-security-and-foreign-policy/"),
            ("Smith Richardson Grants", "https://www.srf.org/apply/"),
            ("Carnegie Corporation", "https://www.carnegie.org/grants/grants-database/"),
            ("MacArthur Foundation", "https://www.macfound.org/programs/"),
            ("Luce Foundation Asia", "https://www.hluce.org/programs/asia/"),
            ("Ploughshares Fund", "https://ploughshares.org/what-we-fund"),
            ("Stanton Foundation", "https://www.stantonfoundation.org/nuclear-security/"),
            ("Open Society Foundations", "https://www.opensocietyfoundations.org/grants"),
            ("US-Japan Foundation", "https://us-jf.org/programs/"),
            ("US-Japan Foundation Grants", "https://us-jf.org/grants/"),
            ("Sasakawa Peace Foundation", "https://www.spf.org/en/grants/"),
            ("Korea Foundation", "https://en.kf.or.kr/"),
            ("Japan Foundation", "https://www.jpf.go.jp/e/project/intel/exchange/"),
            ("Ford Foundation", "https://www.fordfoundation.org/work/our-grants/"),
            ("Hewlett Foundation", "https://hewlett.org/grants/"),
            ("Rockefeller Foundation", "https://www.rockefellerfoundation.org/"),
            ("Taiwan Foundation for Democracy", "https://www.tfd.org.tw/en/grants"),
            ("German Marshall Fund", "https://www.gmfus.org/grants-fellowships"),
        ]

    def _get_think_tank_grant_pages(self) -> List[tuple]:
        """Think tanks that offer grants, fellowships, or funded research positions."""
        return [
            ("CSIS Fellowships", "https://www.csis.org/about-us/careers-internships"),
            ("Brookings Fellowships", "https://www.brookings.edu/careers/"),
            ("RAND Fellowships", "https://www.rand.org/about/edu_op.html"),
            ("CFR Fellowships", "https://www.cfr.org/fellowships"),
            ("Wilson Center Fellowships", "https://www.wilsoncenter.org/fellowships"),
            ("Carnegie Endowment Fellowships", "https://carnegieendowment.org/about/employment"),
            ("Stimson Center", "https://www.stimson.org/about/careers/"),
            ("Atlantic Council Fellowships", "https://www.atlanticcouncil.org/about/employment/"),
            ("Hudson Institute Fellowships", "https://www.hudson.org/about/careers"),
            ("Heritage Foundation Fellowships", "https://www.heritage.org/about-heritage/careers"),
            ("AEI Fellowships", "https://www.aei.org/jobs/"),
            ("IISS Fellowships", "https://www.iiss.org/about-us/careers/"),
            ("Center for a New American Security", "https://www.cnas.org/careers"),
            ("Project 2049 Institute", "https://project2049.net/"),
        ]

    def _get_congressional_sites(self) -> List[tuple]:
        """Congressional commissions and committees that may have funding or RFIs."""
        return [
            ("US-China Economic and Security Review Commission", "https://www.uscc.gov/"),
            ("USCC Research", "https://www.uscc.gov/research"),
            ("Congressional-Executive Commission on China", "https://www.cecc.gov/"),
            ("Congressional Research Service", "https://crsreports.congress.gov/"),
            ("HPSCI (House Intelligence)", "https://intelligence.house.gov/"),
            ("SSCI (Senate Intelligence)", "https://www.intelligence.senate.gov/"),
            ("SFRC (Senate Foreign Relations)", "https://www.foreign.senate.gov/"),
            ("HFAC (House Foreign Affairs)", "https://foreignaffairs.house.gov/"),
            ("HASC (House Armed Services)", "https://armedservices.house.gov/"),
            ("SASC (Senate Armed Services)", "https://www.armed-services.senate.gov/"),
            ("Tom Lantos Human Rights Commission", "https://humanrightscommission.house.gov/"),
            ("Helsinki Commission", "https://www.csce.gov/"),
            ("EastWest Center", "https://www.eastwestcenter.org/grants-and-fellowships"),
            ("National Bureau of Asian Research", "https://www.nbr.org/"),
        ]

    def _scrape_site(self, site_name: str, url: str) -> List[Opportunity]:
        """Scrape a specific funding website for opportunities."""
        cached = self.cache.get(url)
        if cached and isinstance(cached, list):
            return [self._make_opportunity(**o) for o in cached]

        html = self.client.get_text(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        opportunities = self._extract_opportunities_from_page(soup, site_name, url)

        return opportunities

    def _extract_opportunities_from_page(
        self, soup: BeautifulSoup, site_name: str, base_url: str
    ) -> List[Opportunity]:
        """Extract funding opportunities from a parsed HTML page."""
        opportunities = []

        # Strategy 1: Find links with funding-related text
        for link in soup.find_all("a", href=True):
            text = link.get_text(strip=True)
            if len(text) < 10 or len(text) > 300:
                continue

            # Must have grant signal words
            if not GRANT_SIGNAL_WORDS.search(text) and not GRANT_SIGNAL_WORDS.search(link.get("href", "")):
                continue

            # Skip non-grant links
            if NON_GRANT_PATTERNS.search(text):
                continue

            # Skip closed/past opportunities
            parent_text = ""
            parent = link.parent
            if parent:
                parent_text = parent.get_text(strip=True)
            if CLOSED_PATTERNS.search(parent_text):
                continue

            href = link["href"]
            if not href.startswith("http"):
                href = urljoin(base_url, href)
            # Skip non-content links
            if any(skip in href.lower() for skip in ["javascript:", "mailto:", "#", ".pdf"]):
                continue

            opp = self._make_opportunity(
                title=text,
                opportunity_type=self._infer_type(text),
                funder=site_name,
                source_website=urlparse(base_url).netloc,
                listing_url=href,
                application_url=href,
            )
            opportunities.append(opp)

        # Strategy 2: Look for structured listings (cards, list items, etc.)
        for container in soup.find_all(["article", "li", "div"], class_=re.compile(
            r'(grant|opportunity|listing|program|result|card|fellowship|'
            r'solicitation|funding|open|active)', re.IGNORECASE
        )):
            title_el = container.find(["h2", "h3", "h4", "a", "strong"])
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if len(title) < 10:
                continue

            # Skip closed items
            container_text = container.get_text(strip=True)
            if CLOSED_PATTERNS.search(container_text) and not re.search(r'open|active|accepting', container_text, re.IGNORECASE):
                continue

            link_el = container.find("a", href=True)
            href = ""
            if link_el:
                href = link_el["href"]
                if not href.startswith("http"):
                    href = urljoin(base_url, href)

            desc_el = container.find(["p", "span", "div"], class_=re.compile(
                r'(desc|summary|excerpt|body|text)', re.IGNORECASE
            ))
            desc = desc_el.get_text(strip=True) if desc_el else ""

            # Extract deadline if visible
            deadline = ""
            deadline_el = container.find(string=re.compile(r'(deadline|due|closes?|by)', re.IGNORECASE))
            if deadline_el:
                deadline = deadline_el.strip()[:100]

            opp = self._make_opportunity(
                title=title,
                opportunity_type=self._infer_type(title),
                funder=site_name,
                source_website=urlparse(base_url).netloc,
                listing_url=href,
                synopsis=desc[:500],
                deadline=deadline,
            )
            if opp.title not in [o.title for o in opportunities]:
                opportunities.append(opp)

        return opportunities

    def _google_search(self, query: str) -> List[Opportunity]:
        """Execute a targeted web search (uses Google CSE if available)."""
        api_key = os.environ.get("GOOGLE_API_KEY")
        cse_id = os.environ.get("GOOGLE_CSE_ID")

        if api_key and cse_id:
            return self._google_cse_search(query, api_key, cse_id)

        # Fallback: construct direct URL searches
        return []

    def _google_cse_search(self, query: str, api_key: str, cse_id: str) -> List[Opportunity]:
        """Search using Google Custom Search Engine API."""
        opportunities = []
        params = {
            "key": api_key,
            "cx": cse_id,
            "q": query,
            "num": 10,
        }
        data = self.client.get_json(
            "https://www.googleapis.com/customsearch/v1",
            params=params,
        )
        if data and "items" in data:
            for item in data["items"]:
                opp = self._make_opportunity(
                    title=item.get("title", ""),
                    synopsis=item.get("snippet", ""),
                    listing_url=item.get("link", ""),
                    funder=urlparse(item.get("link", "")).netloc,
                    source_website=item.get("displayLink", ""),
                )
                opportunities.append(opp)
        return opportunities

    def _build_search_queries(self, base_queries: List[str]) -> List[str]:
        """Build targeted search queries from base keywords."""
        templates = [
            "{kw} funding opportunity 2025 2026",
            "{kw} grant call for proposals open",
            "{kw} BAA broad agency announcement 2025",
            "{kw} research funding university center 2025",
            "{kw} foundation grant security policy open",
            "{kw} fellowship application open 2025 2026",
            "{kw} cooperative agreement NOFO 2025",
        ]
        queries = []
        for kw in base_queries[:5]:
            for template in templates[:3]:
                queries.append(template.format(kw=kw))
        return queries

    @staticmethod
    def _infer_type(text: str) -> str:
        """Infer opportunity type from title text."""
        text_lower = text.lower()
        if "baa" in text_lower or "broad agency" in text_lower:
            return "BAA"
        if "rfp" in text_lower or "request for proposal" in text_lower:
            return "RFP"
        if "rfi" in text_lower or "request for information" in text_lower:
            return "RFI"
        if "fellowship" in text_lower:
            return "Fellowship"
        if "prize" in text_lower or "challenge" in text_lower or "competition" in text_lower:
            return "Prize"
        if "cooperative" in text_lower:
            return "Cooperative Agreement"
        if "contract" in text_lower:
            return "Contract"
        if "grant" in text_lower or "fund" in text_lower:
            return "Grant"
        if "nofo" in text_lower or "notice of funding" in text_lower:
            return "Grant"
        return "Other"
