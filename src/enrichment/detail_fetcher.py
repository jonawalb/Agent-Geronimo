"""Detail enrichment for discovered opportunities.

Fetches additional details from opportunity pages:
- Full descriptions
- Eligibility details
- Application portals
- Deadlines and amounts
- Related documents
"""
import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from ..models import Opportunity
from ..utils.http_client import RateLimitedClient

logger = logging.getLogger("geronimo.enrichment.detail")


class DetailFetcher:
    """Fetches and enriches opportunity details from listing pages."""

    def __init__(self, client: RateLimitedClient):
        self.client = client

    def enrich(self, opp: Opportunity) -> Opportunity:
        """Enrich an opportunity with additional details from its listing URL."""
        if not opp.listing_url:
            return opp

        try:
            html = self.client.get_text(opp.listing_url)
            if not html:
                return opp

            soup = BeautifulSoup(html, "lxml")
            self._extract_details(opp, soup)
        except Exception as e:
            logger.debug(f"Failed to enrich {opp.title[:50]}: {e}")

        return opp

    def _extract_details(self, opp: Opportunity, soup: BeautifulSoup):
        """Extract structured details from a parsed opportunity page."""
        # Try to find description
        if not opp.full_description:
            desc = self._find_description(soup)
            if desc:
                opp.full_description = desc[:2000]

        # Try to find deadline
        if not opp.deadline:
            deadline = self._find_deadline(soup)
            if deadline:
                opp.deadline = deadline

        # Try to find award amounts
        if not opp.typical_award:
            amount = self._find_amount(soup)
            if amount:
                opp.typical_award = amount

        # Try to find eligibility info
        if not opp.eligibility_text:
            elig = self._find_eligibility(soup)
            if elig:
                opp.eligibility_text = elig
                self._parse_eligibility(opp, elig)

        # Try to find application portal link
        if not opp.application_url:
            portal = self._find_portal_link(soup)
            if portal:
                opp.application_url = portal

    def _find_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Find the main description/synopsis on the page."""
        # Common patterns for description sections
        for selector in [
            {"id": re.compile(r"description|synopsis|overview|summary", re.I)},
            {"class_": re.compile(r"description|synopsis|overview|summary|body|content", re.I)},
        ]:
            el = soup.find(["div", "section", "article", "p"], selector)
            if el:
                text = el.get_text(strip=True)
                if len(text) > 50:
                    return text[:2000]

        # Fall back to largest text block
        paragraphs = soup.find_all("p")
        if paragraphs:
            texts = [p.get_text(strip=True) for p in paragraphs]
            long_texts = [t for t in texts if len(t) > 100]
            if long_texts:
                return " ".join(long_texts[:3])[:2000]

        return None

    def _find_deadline(self, soup: BeautifulSoup) -> Optional[str]:
        """Find deadline date on the page."""
        date_pattern = re.compile(
            r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})|'
            r'(\w+ \d{1,2},? \d{4})|'
            r'(\d{4}[/\-]\d{1,2}[/\-]\d{1,2})'
        )

        # Look for deadline-labeled elements
        for label_text in ["deadline", "close date", "due date", "response date",
                           "closing date", "submission date"]:
            for el in soup.find_all(text=re.compile(label_text, re.I)):
                parent = el.parent if hasattr(el, "parent") else None
                if parent:
                    nearby_text = parent.get_text()
                    match = date_pattern.search(nearby_text)
                    if match:
                        return match.group().strip()

        return None

    def _find_amount(self, soup: BeautifulSoup) -> Optional[str]:
        """Find funding amount on the page."""
        amount_pattern = re.compile(r'\$[\d,]+(?:\.\d{2})?(?:\s*(?:million|M|K|thousand))?')

        for label_text in ["award", "funding", "amount", "ceiling", "floor", "budget"]:
            for el in soup.find_all(text=re.compile(label_text, re.I)):
                parent = el.parent if hasattr(el, "parent") else None
                if parent:
                    text = parent.get_text()
                    match = amount_pattern.search(text)
                    if match:
                        return match.group()

        return None

    def _find_eligibility(self, soup: BeautifulSoup) -> Optional[str]:
        """Find eligibility information on the page."""
        for label_text in ["eligib", "who can apply", "applicant type", "eligible"]:
            for el in soup.find_all(text=re.compile(label_text, re.I)):
                parent = el.parent if hasattr(el, "parent") else None
                if parent:
                    # Get the containing section
                    section = parent.find_parent(["div", "section", "li", "tr"])
                    if section:
                        return section.get_text(strip=True)[:500]
                    return parent.get_text(strip=True)[:500]
        return None

    def _find_portal_link(self, soup: BeautifulSoup) -> Optional[str]:
        """Find application portal link."""
        for link in soup.find_all("a", href=True):
            text = link.get_text(strip=True).lower()
            href = link["href"]
            if any(kw in text for kw in ["apply", "submit", "application", "portal"]):
                if href.startswith("http"):
                    return href
        return None

    @staticmethod
    def _parse_eligibility(opp: Opportunity, elig_text: str):
        """Parse eligibility text to set boolean eligibility fields."""
        text = elig_text.lower()

        if any(kw in text for kw in ["university", "higher education", "academic",
                                      "institution of higher"]):
            opp.universities_eligible = "Yes"
        if any(kw in text for kw in ["research center", "research organization",
                                      "research institution"]):
            opp.research_centers_eligible = "Yes"
        if any(kw in text for kw in ["nonprofit", "non-profit", "501(c)"]):
            opp.nonprofits_eligible = "Yes"
        if any(kw in text for kw in ["think tank", "policy institute", "policy organization"]):
            opp.think_tanks_eligible = "Yes"
        if any(kw in text for kw in ["university-affiliated", "university center",
                                      "university-based"]):
            opp.university_centers_eligible = "Yes"
        if any(kw in text for kw in ["u.s. citizen", "us citizen", "clearance",
                                      "security clearance"]):
            opp.citizenship_restrictions = "US citizens / clearance may be required"
