"""Past award analysis for funder intelligence.

Analyzes previously funded projects to infer funder preferences,
typical award sizes, favored institutions, and successful framing.
"""
import logging
from typing import Dict, List, Optional

from ..models import Opportunity
from ..utils.http_client import RateLimitedClient
from ..utils.cache import Cache

logger = logging.getLogger("geronimo.enrichment.awards")


# Known funder profiles (pre-seeded intelligence)
FUNDER_PROFILES: Dict[str, Dict] = {
    "smith richardson foundation": {
        "typical_award": "$50,000 - $250,000",
        "project_length": "1-2 years",
        "preferences": (
            "Prefers applied policy impact over pure theory. "
            "Values security, defense, and foreign policy research. "
            "Historically funds think tanks, university centers, and individual scholars. "
            "Strong interest in strategic studies, military affairs, and international security."
        ),
        "favored_language": "strategic, policy-relevant, national security, defense, applied research",
        "common_winners": "Think tanks (RAND, CSIS, Hudson), university policy centers, senior scholars",
    },
    "carnegie corporation": {
        "typical_award": "$100,000 - $500,000",
        "project_length": "1-3 years",
        "preferences": (
            "Focuses on international peace and security, democracy, and higher education. "
            "Values interdisciplinary approaches and public engagement. "
            "Increasingly interested in technology and security intersection."
        ),
        "favored_language": "peace, security, democracy, nuclear, technology, international order",
        "common_winners": "Major universities, established think tanks, international organizations",
    },
    "henry luce foundation": {
        "typical_award": "$50,000 - $300,000",
        "project_length": "1-3 years",
        "preferences": (
            "Strong Asia focus. Funds Asia studies, policy research, and educational programs. "
            "Values deep regional expertise and cross-cultural understanding."
        ),
        "favored_language": "Asia, Pacific, religion, public policy, higher education",
        "common_winners": "Universities, Asia-focused research centers, cultural organizations",
    },
    "ned": {
        "typical_award": "$50,000 - $200,000",
        "project_length": "1-2 years",
        "preferences": (
            "Focuses on democracy promotion and human rights. "
            "Values civil society strengthening, media freedom, democratic governance. "
            "Active in regions facing authoritarian pressure."
        ),
        "favored_language": "democracy, human rights, civil society, governance, freedom",
        "common_winners": "NGOs, civil society organizations, media organizations, think tanks",
    },
    "ploughshares fund": {
        "typical_award": "$25,000 - $150,000",
        "project_length": "1-2 years",
        "preferences": (
            "Nuclear security and arms control focus. "
            "Values policy advocacy and public education on nuclear threats."
        ),
        "favored_language": "nuclear, arms control, nonproliferation, security, policy",
        "common_winners": "Arms control organizations, policy institutes, advocacy groups",
    },
    "macarthur foundation": {
        "typical_award": "$100,000 - $1,000,000",
        "project_length": "1-5 years",
        "preferences": (
            "Broad scope including nuclear risk, climate, criminal justice. "
            "Values bold ideas, systemic change, and long-term impact. "
            "Big Bets program funds major initiatives."
        ),
        "favored_language": "systemic change, nuclear risk, climate, justice, innovation",
        "common_winners": "Major research institutions, advocacy organizations, universities",
    },
    "minerva research initiative": {
        "typical_award": "$500,000 - $2,500,000",
        "project_length": "3-5 years",
        "preferences": (
            "DoD social science research. Values rigorous methodology, "
            "policy relevance to defense, and university-based research teams. "
            "Emphasis on understanding social, cultural, and political dynamics "
            "relevant to national security."
        ),
        "favored_language": (
            "social science, security, cultural dynamics, political violence, "
            "strategic competition, information environment"
        ),
        "common_winners": "Major research universities, multi-institution teams",
    },
    "darpa": {
        "typical_award": "$1,000,000 - $10,000,000+",
        "project_length": "2-5 years",
        "preferences": (
            "Breakthrough technology and high-risk/high-reward research. "
            "Values technical innovation, novel approaches, and transformative potential."
        ),
        "favored_language": "breakthrough, transformative, novel, high-risk, technology, innovation",
        "common_winners": "Defense contractors, major universities, specialized tech companies",
    },
    "stanton foundation": {
        "typical_award": "$50,000 - $200,000",
        "project_length": "1-2 years",
        "preferences": (
            "Nuclear policy fellows and security research. "
            "Values next-generation scholars in nuclear/security policy."
        ),
        "favored_language": "nuclear, security, policy, fellow, next generation",
        "common_winners": "Universities, policy institutes with nuclear focus",
    },
}


class AwardAnalyzer:
    """Analyzes past awards and funder profiles for intelligence."""

    def __init__(self, client: RateLimitedClient, cache: Cache):
        self.client = client
        self.cache = cache

    def enrich_with_funder_intelligence(self, opp: Opportunity) -> Opportunity:
        """Add funder intelligence to an opportunity."""
        funder_key = (opp.funder or "").lower().strip()

        # Check pre-seeded profiles
        for profile_key, profile in FUNDER_PROFILES.items():
            if profile_key in funder_key or funder_key in profile_key:
                opp.typical_award = opp.typical_award or profile.get("typical_award", "")
                opp.project_length = opp.project_length or profile.get("project_length", "")
                opp.funder_preferences = profile.get("preferences", "")
                opp.prior_awardees = profile.get("common_winners", "")

                # Add to notes
                favored = profile.get("favored_language", "")
                if favored:
                    opp.notes = (
                        (opp.notes or "") +
                        f" [Funder favors: {favored}]"
                    ).strip()
                break

        return opp

    def search_past_awards(self, funder: str, keywords: List[str]) -> List[Dict]:
        """Search for past awards from a specific funder."""
        # Use USAspending API for federal funders
        if any(kw in funder.lower() for kw in ["dod", "defense", "army", "navy",
                                                  "air force", "darpa", "dhs", "state",
                                                  "nsf", "doe"]):
            return self._search_usaspending(funder, keywords)
        return []

    def _search_usaspending(self, funder: str, keywords: List[str]) -> List[Dict]:
        """Query USAspending for past award data."""
        cache_key = f"awards_{funder}_{'-'.join(keywords[:3])}"
        cached = self.cache.get("usaspending_awards", {"key": cache_key})
        if cached:
            return cached.get("results", [])

        payload = {
            "filters": {
                "keywords": keywords[:5],
                "time_period": [
                    {"start_date": "2020-01-01", "end_date": "2026-12-31"}
                ],
            },
            "fields": [
                "Award ID", "Recipient Name", "Description",
                "Award Amount", "Awarding Agency",
            ],
            "limit": 20,
            "sort": "Award Amount",
            "order": "desc",
        }

        resp = self.client.post(
            "https://api.usaspending.gov/api/v2/search/spending_by_award",
            json=payload,
        )
        if resp:
            try:
                data = resp.json()
                results = data.get("results", [])
                self.cache.set("usaspending_awards", {"results": results},
                              params={"key": cache_key})
                return results
            except Exception:
                pass
        return []
