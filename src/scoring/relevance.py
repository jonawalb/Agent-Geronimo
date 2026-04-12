"""Multi-dimensional relevance scoring for funding opportunities.

Scores each opportunity across three lenses:
1. TSM fit (Taiwan Security Monitor)
2. GMU national security center fit
3. General security studies / think tank fit

Also generates framing recommendations and proposal angles.
"""
import logging
import re
from typing import Dict, List, Tuple

from ..models import Opportunity

logger = logging.getLogger("geronimo.scoring.relevance")


# Keyword groups with weights for each scoring lens
# Higher weight = stronger signal for that lens
KEYWORD_WEIGHTS: Dict[str, Dict[str, float]] = {
    # --- TSM-specific ---
    "taiwan": {"tsm": 25, "gmu": 8, "general": 5},
    "taiwan strait": {"tsm": 25, "gmu": 10, "general": 8},
    "cross-strait": {"tsm": 25, "gmu": 10, "general": 8},
    "taiwan security": {"tsm": 30, "gmu": 10, "general": 8},
    "prc": {"tsm": 15, "gmu": 8, "general": 5},
    "pla": {"tsm": 20, "gmu": 10, "general": 8},
    "adiz": {"tsm": 20, "gmu": 5, "general": 3},
    "taiwan monitor": {"tsm": 30, "gmu": 5, "general": 3},

    # --- Indo-Pacific ---
    "indo-pacific": {"tsm": 18, "gmu": 15, "general": 12},
    "indo pacific": {"tsm": 18, "gmu": 15, "general": 12},
    "asia pacific": {"tsm": 15, "gmu": 12, "general": 10},
    "east asia": {"tsm": 15, "gmu": 12, "general": 10},
    "south china sea": {"tsm": 18, "gmu": 12, "general": 10},
    "pacific deterrence": {"tsm": 18, "gmu": 15, "general": 12},
    "china": {"tsm": 12, "gmu": 10, "general": 8},

    # --- Information / Narrative Warfare ---
    "information warfare": {"tsm": 20, "gmu": 18, "general": 15},
    "information operations": {"tsm": 18, "gmu": 16, "general": 14},
    "influence operations": {"tsm": 18, "gmu": 16, "general": 14},
    "disinformation": {"tsm": 18, "gmu": 15, "general": 12},
    "misinformation": {"tsm": 15, "gmu": 12, "general": 10},
    "narrative warfare": {"tsm": 22, "gmu": 15, "general": 12},
    "cognitive warfare": {"tsm": 20, "gmu": 18, "general": 15},
    "psychological operations": {"tsm": 15, "gmu": 15, "general": 12},
    "propaganda": {"tsm": 15, "gmu": 12, "general": 10},
    "strategic communications": {"tsm": 18, "gmu": 15, "general": 12},
    "media manipulation": {"tsm": 15, "gmu": 12, "general": 10},
    "computational propaganda": {"tsm": 15, "gmu": 12, "general": 10},

    # --- OSINT / GEOINT ---
    "osint": {"tsm": 22, "gmu": 15, "general": 10},
    "open source intelligence": {"tsm": 22, "gmu": 15, "general": 10},
    "geoint": {"tsm": 18, "gmu": 15, "general": 10},
    "geospatial": {"tsm": 15, "gmu": 12, "general": 8},
    "remote sensing": {"tsm": 12, "gmu": 10, "general": 8},

    # --- Security / Defense (broad) ---
    "national security": {"tsm": 12, "gmu": 20, "general": 18},
    "security studies": {"tsm": 10, "gmu": 20, "general": 18},
    "strategic studies": {"tsm": 12, "gmu": 20, "general": 18},
    "defense": {"tsm": 10, "gmu": 18, "general": 15},
    "defense analysis": {"tsm": 10, "gmu": 18, "general": 15},
    "defense research": {"tsm": 10, "gmu": 18, "general": 15},
    "defense innovation": {"tsm": 10, "gmu": 18, "general": 15},
    "military": {"tsm": 10, "gmu": 15, "general": 12},
    "military affairs": {"tsm": 10, "gmu": 15, "general": 12},
    "deterrence": {"tsm": 15, "gmu": 18, "general": 15},
    "arms control": {"tsm": 8, "gmu": 15, "general": 12},
    "nuclear": {"tsm": 8, "gmu": 15, "general": 12},

    # --- Strategic Competition ---
    "strategic competition": {"tsm": 15, "gmu": 18, "general": 15},
    "great power competition": {"tsm": 15, "gmu": 18, "general": 15},
    "great power": {"tsm": 12, "gmu": 15, "general": 12},
    "strategic rivalry": {"tsm": 12, "gmu": 15, "general": 12},

    # --- Intelligence ---
    "intelligence": {"tsm": 12, "gmu": 18, "general": 15},
    "intelligence analysis": {"tsm": 15, "gmu": 18, "general": 15},
    "intelligence community": {"tsm": 10, "gmu": 15, "general": 12},
    "strategic warning": {"tsm": 15, "gmu": 15, "general": 12},
    "early warning": {"tsm": 15, "gmu": 12, "general": 10},

    # --- Cyber / Tech ---
    "cybersecurity": {"tsm": 10, "gmu": 15, "general": 12},
    "cyber": {"tsm": 8, "gmu": 12, "general": 10},
    "technology and security": {"tsm": 10, "gmu": 15, "general": 12},
    "emerging technology": {"tsm": 10, "gmu": 15, "general": 12},
    "artificial intelligence": {"tsm": 8, "gmu": 12, "general": 10},
    "critical infrastructure": {"tsm": 8, "gmu": 12, "general": 10},

    # --- Resilience / Democracy ---
    "democratic resilience": {"tsm": 12, "gmu": 15, "general": 12},
    "resilience": {"tsm": 10, "gmu": 12, "general": 10},
    "democracy": {"tsm": 8, "gmu": 12, "general": 10},
    "governance": {"tsm": 5, "gmu": 12, "general": 10},
    "authoritarian": {"tsm": 12, "gmu": 12, "general": 10},

    # --- Policy / Analysis ---
    "foreign policy": {"tsm": 10, "gmu": 15, "general": 15},
    "policy research": {"tsm": 8, "gmu": 18, "general": 15},
    "policy center": {"tsm": 8, "gmu": 20, "general": 15},
    "policy analysis": {"tsm": 8, "gmu": 18, "general": 15},
    "conflict analysis": {"tsm": 12, "gmu": 15, "general": 12},
    "geopolitical risk": {"tsm": 12, "gmu": 15, "general": 12},
    "decision support": {"tsm": 15, "gmu": 15, "general": 10},
    "public opinion": {"tsm": 12, "gmu": 12, "general": 10},

    # --- Wargaming / Simulation ---
    "wargaming": {"tsm": 15, "gmu": 18, "general": 15},
    "wargame": {"tsm": 15, "gmu": 18, "general": 15},
    "simulation": {"tsm": 10, "gmu": 15, "general": 12},
    "tabletop exercise": {"tsm": 12, "gmu": 15, "general": 12},
    "red team": {"tsm": 10, "gmu": 15, "general": 12},
    "scenario planning": {"tsm": 10, "gmu": 12, "general": 10},

    # --- Hybrid / Gray Zone ---
    "gray zone": {"tsm": 15, "gmu": 18, "general": 15},
    "hybrid": {"tsm": 12, "gmu": 15, "general": 12},
    "irregular warfare": {"tsm": 10, "gmu": 15, "general": 12},
    "political warfare": {"tsm": 15, "gmu": 15, "general": 12},

    # --- Institutional / Center ---
    "university center": {"tsm": 5, "gmu": 20, "general": 15},
    "research center": {"tsm": 5, "gmu": 20, "general": 15},
    "think tank": {"tsm": 8, "gmu": 15, "general": 18},
    "academic policy": {"tsm": 5, "gmu": 18, "general": 15},
    "workshop": {"tsm": 8, "gmu": 12, "general": 10},
    "briefing": {"tsm": 10, "gmu": 12, "general": 8},
    "analytical product": {"tsm": 15, "gmu": 12, "general": 8},

    # --- Eligibility boosters ---
    "nonprofit": {"tsm": 5, "gmu": 8, "general": 8},
    "university": {"tsm": 3, "gmu": 10, "general": 8},
    "higher education": {"tsm": 3, "gmu": 10, "general": 5},
}


def score_opportunity(opp: Opportunity) -> Opportunity:
    """Score an opportunity across all three fit lenses and add metadata."""
    text = _build_text_corpus(opp)
    text_lower = text.lower()

    tsm_score = 0
    gmu_score = 0
    general_score = 0
    matched_keywords = []

    for keyword, weights in KEYWORD_WEIGHTS.items():
        kw_lower = keyword.lower()
        if kw_lower in text_lower:
            tsm_score += weights["tsm"]
            gmu_score += weights["gmu"]
            general_score += weights["general"]
            matched_keywords.append(keyword)
        else:
            # Partial word matching for single-word keywords in titles
            # e.g. "cybersecurity" should match "Cybersecurity Innovation"
            kw_words = kw_lower.split()
            if len(kw_words) == 1 and len(kw_lower) >= 5:
                # Check if any word in text starts with this keyword or vice versa
                text_words = set(re.findall(r'\b\w+\b', text_lower))
                for tw in text_words:
                    if (tw.startswith(kw_lower) or kw_lower.startswith(tw)) and len(tw) >= 5:
                        tsm_score += weights["tsm"] // 2
                        gmu_score += weights["gmu"] // 2
                        general_score += weights["general"] // 2
                        matched_keywords.append(f"{keyword}~")
                        break

    # Cap at 100
    opp.tsm_fit_score = min(100, tsm_score)
    opp.gmu_center_fit_score = min(100, gmu_score)
    opp.general_security_fit_score = min(100, general_score)

    # Overall weighted score
    opp.overall_relevance_score = min(100, int(
        opp.tsm_fit_score * 0.35 +
        opp.gmu_center_fit_score * 0.35 +
        opp.general_security_fit_score * 0.30
    ))

    # Confidence based on how much data we have
    opp.confidence_score = _calculate_confidence(opp)

    # Set relevance tags
    opp.keywords = "; ".join(matched_keywords[:15])
    _set_relevance_tags(opp, text_lower)

    # Competitiveness and difficulty estimates
    opp.estimated_competitiveness = _estimate_competitiveness(opp)
    opp.estimated_difficulty = _estimate_difficulty(opp)

    # Generate framing recommendations
    _generate_recommendations(opp, matched_keywords)

    # Urgency
    opp.urgency = _calculate_urgency(opp)

    # Final recommendation
    opp.final_recommendation = _final_recommendation(opp)

    return opp


def _build_text_corpus(opp: Opportunity) -> str:
    """Combine all text fields for keyword matching."""
    return " ".join(filter(None, [
        opp.title,
        opp.title,  # double-weight titles since they're often the only text
        opp.synopsis,
        opp.full_description,
        opp.topic_area,
        opp.eligibility_text,
        opp.funder,
        opp.sub_agency,
        opp.opportunity_type,
        opp.notes,
    ]))


def _calculate_confidence(opp: Opportunity) -> int:
    """Calculate confidence score based on data completeness."""
    score = 20  # Base
    if opp.title:
        score += 15
    if opp.synopsis or opp.full_description:
        score += 15
    if opp.listing_url:
        score += 10
    if opp.deadline:
        score += 10
    if opp.funder:
        score += 10
    if opp.eligibility_text:
        score += 10
    if opp.award_min or opp.award_max or opp.typical_award:
        score += 10
    return min(100, score)


def _set_relevance_tags(opp: Opportunity, text: str):
    """Set individual relevance category tags."""
    if any(kw in text for kw in ["defense", "military", "dod", "army", "navy", "air force"]):
        opp.security_defense_relevance = "High"
    elif any(kw in text for kw in ["security", "strategic"]):
        opp.security_defense_relevance = "Medium"
    else:
        opp.security_defense_relevance = "Low"

    if any(kw in text for kw in ["taiwan", "cross-strait", "pla", "adiz"]):
        opp.taiwan_relevance = "High"
    elif any(kw in text for kw in ["china", "prc", "beijing"]):
        opp.taiwan_relevance = "Medium"
    else:
        opp.taiwan_relevance = "Low"

    if any(kw in text for kw in ["indo-pacific", "indo pacific", "asia pacific", "east asia", "south china sea"]):
        opp.indo_pacific_relevance = "High"
    elif any(kw in text for kw in ["asia", "pacific", "japan", "korea", "philippines"]):
        opp.indo_pacific_relevance = "Medium"
    else:
        opp.indo_pacific_relevance = "Low"

    if any(kw in text for kw in ["information warfare", "influence operations", "disinformation",
                                  "narrative", "cognitive warfare", "propaganda"]):
        opp.info_warfare_relevance = "High"
    elif any(kw in text for kw in ["information", "media", "communication"]):
        opp.info_warfare_relevance = "Medium"
    else:
        opp.info_warfare_relevance = "Low"

    if any(kw in text for kw in ["cyber", "technology and security", "emerging technology",
                                  "critical infrastructure"]):
        opp.cyber_tech_relevance = "High"
    elif any(kw in text for kw in ["technology", "digital", "data"]):
        opp.cyber_tech_relevance = "Medium"
    else:
        opp.cyber_tech_relevance = "Low"

    if any(kw in text for kw in ["policy center", "research center", "university center",
                                  "think tank", "policy research"]):
        opp.policy_center_relevance = "High"
    elif any(kw in text for kw in ["policy", "research", "analysis"]):
        opp.policy_center_relevance = "Medium"
    else:
        opp.policy_center_relevance = "Low"


def _estimate_competitiveness(opp: Opportunity) -> str:
    """Estimate how competitive the opportunity is."""
    text = (opp.title + " " + opp.synopsis + " " + opp.funder).lower()

    if any(kw in text for kw in ["darpa", "iarpa", "diu"]):
        return "Very High"
    if any(kw in text for kw in ["nsf", "nih", "doe"]):
        return "High"
    if any(kw in text for kw in ["foundation", "endowment"]):
        return "Medium-High"
    if any(kw in text for kw in ["dhs", "state department", "drl", "ned"]):
        return "Medium"
    if any(kw in text for kw in ["sbir", "sttr"]):
        return "Medium"
    return "Unknown"


def _estimate_difficulty(opp: Opportunity) -> str:
    """Estimate application difficulty."""
    text = (opp.title + " " + opp.synopsis + " " + opp.funder).lower()
    opp_type = opp.opportunity_type.lower()

    if opp_type in ["baa", "contract", "rfp"]:
        return "High"
    if any(kw in text for kw in ["full proposal", "technical volume"]):
        return "High"
    if opp_type == "rfi":
        return "Low"
    if opp_type in ["fellowship", "prize"]:
        return "Medium"
    if any(kw in text for kw in ["letter of inquiry", "concept note", "white paper"]):
        return "Low-Medium"
    return "Medium"


def _generate_recommendations(opp: Opportunity, matched_keywords: List[str]):
    """Generate framing and proposal recommendations."""
    text_lower = (opp.title + " " + opp.synopsis).lower()

    # TSM framing
    tsm_angles = []
    if opp.tsm_fit_score >= 40:
        if any(kw in matched_keywords for kw in ["taiwan", "taiwan strait", "cross-strait", "pla", "adiz"]):
            tsm_angles.append("Direct Taiwan focus — foreground TSM's monitoring, OSINT, and analytical products")
        if any(kw in matched_keywords for kw in ["information warfare", "disinformation", "narrative warfare",
                                                   "cognitive warfare", "influence operations"]):
            tsm_angles.append("Frame around TSM's information/narrative warfare analysis capabilities")
        if any(kw in matched_keywords for kw in ["osint", "geoint", "open source intelligence", "geospatial"]):
            tsm_angles.append("Emphasize OSINT/GEOINT methodology and data-driven analysis")
        if any(kw in matched_keywords for kw in ["indo-pacific", "asia pacific", "east asia"]):
            tsm_angles.append("Position TSM as Indo-Pacific regional security analysis provider")
        if any(kw in matched_keywords for kw in ["deterrence", "strategic competition", "great power"]):
            tsm_angles.append("Frame deterrence/competition angle through Taiwan lens")
    if tsm_angles:
        opp.suggested_framing_tsm = "; ".join(tsm_angles)
    else:
        opp.suggested_framing_tsm = "Low direct TSM alignment — consider if broadened scope fits"

    # GMU/CSPS framing
    gmu_angles = []
    if opp.gmu_center_fit_score >= 40:
        if any(kw in matched_keywords for kw in ["policy center", "research center", "university center"]):
            gmu_angles.append("Strong center-funding fit — frame as GMU Schar School initiative")
        if any(kw in matched_keywords for kw in ["national security", "security studies", "strategic studies"]):
            gmu_angles.append("Core security studies alignment — emphasize CSPS research program")
        if any(kw in matched_keywords for kw in ["wargaming", "simulation", "tabletop"]):
            gmu_angles.append("Wargaming/simulation capability — frame as applied research with policy impact")
        gmu_angles.append("Leverage GMU's proximity to DC policy community and defense establishment")
    if gmu_angles:
        opp.suggested_framing_gmu = "; ".join(gmu_angles)
    else:
        opp.suggested_framing_gmu = "Moderate fit — may need broader framing under Schar School programs"

    # Proposal angle
    if opp.overall_relevance_score >= 60:
        opp.suggested_proposal_angle = _generate_proposal_angle(opp, matched_keywords)
    elif opp.overall_relevance_score >= 30:
        opp.suggested_proposal_angle = "Consider as secondary target — may fit with broader center programming"

    # Concept paragraph
    if opp.overall_relevance_score >= 50:
        opp.suggested_concept_paragraph = _generate_concept(opp, matched_keywords)

    # Lead type
    opp.recommended_lead_type = _recommend_lead(opp)

    # Next step
    opp.recommended_next_step = _recommend_next_step(opp)


def _generate_proposal_angle(opp: Opportunity, keywords: List[str]) -> str:
    """Generate a suggested proposal angle."""
    angles = []
    if "taiwan" in keywords or "indo-pacific" in keywords:
        angles.append("Taiwan/Indo-Pacific security analysis and monitoring")
    if any(kw in keywords for kw in ["information warfare", "disinformation", "narrative warfare"]):
        angles.append("information environment analysis and resilience")
    if any(kw in keywords for kw in ["osint", "geoint"]):
        angles.append("OSINT/GEOINT-driven decision support and analytical products")
    if any(kw in keywords for kw in ["wargaming", "simulation"]):
        angles.append("applied wargaming and scenario analysis")
    if any(kw in keywords for kw in ["deterrence", "strategic competition"]):
        angles.append("deterrence analysis and strategic competition assessment")
    if any(kw in keywords for kw in ["cyber", "technology"]):
        angles.append("technology-security nexus and emerging threat analysis")

    if angles:
        return f"Propose: {'; '.join(angles[:3])}"
    return "General security studies alignment — develop specific angle based on funder priorities"


def _generate_concept(opp: Opportunity, keywords: List[str]) -> str:
    """Generate a one-paragraph concept suggestion."""
    parts = []
    if any(kw in keywords for kw in ["taiwan", "cross-strait", "pla"]):
        parts.append(
            "This project would leverage TSM's established Taiwan security monitoring "
            "infrastructure and analytical products to deliver"
        )
    else:
        parts.append(
            "This project would combine university-based research expertise with "
            "applied analytical capabilities to deliver"
        )

    if any(kw in keywords for kw in ["osint", "geoint", "data"]):
        parts.append("data-driven, OSINT-informed assessments")
    elif any(kw in keywords for kw in ["information warfare", "disinformation"]):
        parts.append("systematic analysis of information threats and resilience measures")
    elif any(kw in keywords for kw in ["wargaming", "simulation"]):
        parts.append("applied wargaming exercises and scenario-based analysis")
    else:
        parts.append("rigorous policy-relevant research and analytical outputs")

    parts.append(
        "supporting decision-makers in government, defense, and policy communities. "
        "Outputs would include regular analytical products, briefings, and public-facing reports."
    )
    return " ".join(parts)


def _recommend_lead(opp: Opportunity) -> str:
    """Recommend who should lead the application."""
    opp_type = opp.opportunity_type.lower()
    if opp_type in ["contract", "baa", "rfp"]:
        return "University office / sponsored programs (may need prime contractor partner)"
    if opp_type == "fellowship":
        return "PI / individual researcher"
    if "center" in (opp.title + opp.synopsis).lower():
        return "Policy center director"
    if opp.gmu_center_fit_score > opp.tsm_fit_score:
        return "University research team / Schar School"
    return "PI or policy center, depending on scope"


def _recommend_next_step(opp: Opportunity) -> str:
    """Recommend immediate next step."""
    if opp.overall_relevance_score >= 70:
        return "HIGH PRIORITY: Review full solicitation, draft concept note, identify PI"
    if opp.overall_relevance_score >= 50:
        return "Review solicitation details, assess eligibility, consider teaming options"
    if opp.overall_relevance_score >= 30:
        return "Track for future cycles, note for center programming alignment"
    return "Low priority — file for reference"


def _calculate_urgency(opp: Opportunity) -> str:
    """Calculate urgency based on deadline proximity."""
    from datetime import datetime, date
    import re

    if not opp.deadline:
        return "Unknown"

    # Try to parse deadline
    deadline_str = opp.deadline.strip()
    for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y",
                "%m-%d-%Y", "%d %B %Y", "%m/%d/%y"]:
        try:
            dl = datetime.strptime(deadline_str, fmt).date()
            days_left = (dl - date.today()).days
            if days_left < 0:
                return "EXPIRED"
            if days_left <= 14:
                return "URGENT (< 2 weeks)"
            if days_left <= 30:
                return "Soon (< 1 month)"
            if days_left <= 90:
                return "Moderate (1-3 months)"
            return "Ample time (3+ months)"
        except ValueError:
            continue

    return "Check deadline"


def _final_recommendation(opp: Opportunity) -> str:
    """Determine final recommendation."""
    score = opp.overall_relevance_score
    if score >= 50:
        return "Apply"
    if score >= 30:
        return "Consider"
    if score >= 18:
        return "Track"
    if score >= 10:
        return "Low fit"
    return "Low fit"
