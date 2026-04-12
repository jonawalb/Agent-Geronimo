"""Web search-based discovery for sources without APIs.

Uses targeted Google searches and direct website scraping to find
opportunities from foundations, agencies, and other sources that
don't provide structured APIs.
"""
import logging
import re
import os
from typing import List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import BaseScraper
from ..models import Opportunity, SourceResult

logger = logging.getLogger("geronimo.discovery.web_search")


class WebSearchScraper(BaseScraper):
    """Discovery via web search and targeted site scraping."""

    source_name = "Web Search"

    def search(self, queries: List[str]) -> SourceResult:
        """Run targeted web searches for funding opportunities."""
        result = SourceResult(source_name=self.source_name)

        # Targeted site searches
        target_sites = [
            ("Smith Richardson Foundation", "https://www.srf.org/programs/international-security-and-foreign-policy/"),
            ("Carnegie Corporation", "https://www.carnegie.org/grants/grants-database/"),
            ("NED", "https://www.ned.org/apply-for-grant/en/"),
            ("MacArthur Foundation", "https://www.macfound.org/programs/"),
            ("Luce Foundation", "https://www.hluce.org/programs/asia/"),
            ("Ploughshares Fund", "https://ploughshares.org/what-we-fund"),
            ("Stanton Foundation", "https://www.stantonfoundation.org/nuclear-security/"),
            ("Open Society Foundations", "https://www.opensocietyfoundations.org/grants"),
            ("Minerva Research Initiative", "https://minerva.defense.gov/Research/Funded-Projects/"),
            ("DARPA", "https://www.darpa.mil/work-with-us/opportunities"),
            ("DIU", "https://www.diu.mil/work-with-us"),
            ("Challenge.gov", "https://www.challenge.gov/?state=open"),
        ]

        for site_name, url in target_sites:
            result.query_count += 1
            try:
                opps = self._scrape_site(site_name, url)
                result.opportunities.extend(opps)
                result.result_count += len(opps)
            except Exception as e:
                logger.warning(f"Failed to scrape {site_name}: {e}")
                result.errors.append(f"{site_name}: {e}")

        # Additional keyword-driven web searches
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

    def _scrape_site(self, site_name: str, url: str) -> List[Opportunity]:
        """Scrape a specific funding website for opportunities."""
        opportunities = []
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

        # Look for common patterns: links with funding-related text
        funding_patterns = re.compile(
            r'(grant|fund|fellowship|call for|proposal|solicitation|opportunity|'
            r'apply|application|rfp|baa|nofo|announcement|program)',
            re.IGNORECASE,
        )

        # Strategy 1: Find links with funding-related text
        for link in soup.find_all("a", href=True):
            text = link.get_text(strip=True)
            if len(text) < 10 or len(text) > 300:
                continue
            if funding_patterns.search(text) or funding_patterns.search(link.get("href", "")):
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
            r'(grant|opportunity|listing|program|result|card)', re.IGNORECASE
        )):
            title_el = container.find(["h2", "h3", "h4", "a", "strong"])
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if len(title) < 10:
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

            opp = self._make_opportunity(
                title=title,
                opportunity_type=self._infer_type(title),
                funder=site_name,
                source_website=urlparse(base_url).netloc,
                listing_url=href,
                synopsis=desc[:500],
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
            "{kw} grant call for proposals",
            "{kw} BAA broad agency announcement",
            "{kw} research funding university center",
            "{kw} foundation grant security policy",
        ]
        queries = []
        for kw in base_queries[:5]:
            for template in templates[:2]:
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
        return "Other"
