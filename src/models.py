"""Data models for funding opportunities."""
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from typing import Optional


@dataclass
class Opportunity:
    """Represents a single funding opportunity with all metadata."""

    # Identity
    opportunity_id: str = ""
    title: str = ""
    opportunity_type: str = ""  # Grant, Contract, BAA, RFP, RFI, etc.

    # Source
    funder: str = ""
    sub_agency: str = ""
    source_website: str = ""
    listing_url: str = ""
    application_url: str = ""

    # Description
    synopsis: str = ""
    full_description: str = ""

    # Eligibility
    eligibility_text: str = ""
    universities_eligible: str = ""
    research_centers_eligible: str = ""
    nonprofits_eligible: str = ""
    think_tanks_eligible: str = ""
    university_centers_eligible: str = ""
    geographic_restrictions: str = ""
    citizenship_restrictions: str = ""

    # Classification
    topic_area: str = ""
    keywords: str = ""
    security_defense_relevance: str = ""
    taiwan_relevance: str = ""
    indo_pacific_relevance: str = ""
    info_warfare_relevance: str = ""
    cyber_tech_relevance: str = ""
    policy_center_relevance: str = ""

    # Scores
    tsm_fit_score: int = 0
    gmu_center_fit_score: int = 0
    general_security_fit_score: int = 0
    overall_relevance_score: int = 0
    confidence_score: int = 0
    estimated_competitiveness: str = ""
    estimated_difficulty: str = ""

    # Dates
    deadline: str = ""
    open_date: str = ""
    recurring_cycle: str = ""

    # Funding
    award_min: str = ""
    award_max: str = ""
    typical_award: str = ""
    cost_share: str = ""
    project_length: str = ""
    num_awards_expected: str = ""

    # Funder Intelligence
    prior_awardees: str = ""
    prior_awardee_links: str = ""
    similar_projects: str = ""
    similar_project_summaries: str = ""
    funder_preferences: str = ""

    # Recommendations
    suggested_framing_tsm: str = ""
    suggested_framing_gmu: str = ""
    suggested_proposal_angle: str = ""
    suggested_concept_paragraph: str = ""
    suggested_outline: str = ""
    recommended_lead_type: str = ""
    recommended_next_step: str = ""
    urgency: str = ""

    # Notes
    notes: str = ""
    red_flags: str = ""

    # Metadata
    data_verified_date: str = ""
    scrape_date: str = ""
    last_updated: str = ""
    source_citations: str = ""

    # TSM Pipeline Fit
    tsm_pipeline_fit: str = ""
    tsm_pipeline_explanation: str = ""
    existing_concept_match: str = ""
    internal_file_references: str = ""
    final_recommendation: str = ""  # Apply, Consider, Track, Low fit, etc.

    # Special column
    why_this_could_work: str = ""

    # Internal tracking
    source_name: str = ""
    raw_data: str = field(default="", repr=False)
    dedup_key: str = ""
    all_source_urls: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for DataFrame creation."""
        d = asdict(self)
        # Remove internal fields from export
        d.pop("raw_data", None)
        d.pop("dedup_key", None)
        return d

    def generate_dedup_key(self) -> str:
        """Generate a normalized key for deduplication."""
        import re
        title_norm = re.sub(r'[^a-z0-9]', '', self.title.lower().strip())
        funder_norm = re.sub(r'[^a-z0-9]', '', self.funder.lower().strip())
        self.dedup_key = f"{funder_norm}_{title_norm}_{self.opportunity_id}"
        return self.dedup_key


@dataclass
class SourceResult:
    """Result from a single source query."""
    source_name: str
    opportunities: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    query_count: int = 0
    result_count: int = 0
    duration_seconds: float = 0.0
    success: bool = True


@dataclass
class RunStats:
    """Statistics for a complete Agent Geronimo run."""
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    total_raw: int = 0
    total_deduped: int = 0
    high_priority_tsm: int = 0
    high_priority_gmu: int = 0
    federal_count: int = 0
    foundation_count: int = 0
    sources_queried: int = 0
    sources_successful: int = 0
    sources_failed: int = 0
    errors: list = field(default_factory=list)

    def summary(self) -> str:
        """Generate human-readable run summary."""
        duration = ""
        if self.end_time:
            dur = self.end_time - self.start_time
            duration = f"{dur.total_seconds():.0f}s"
        return (
            f"\n{'='*60}\n"
            f"  AGENT GERONIMO - RUN SUMMARY\n"
            f"{'='*60}\n"
            f"  Total raw opportunities found:     {self.total_raw}\n"
            f"  Total after deduplication:          {self.total_deduped}\n"
            f"  High-priority TSM opportunities:    {self.high_priority_tsm}\n"
            f"  High-priority GMU center opps:      {self.high_priority_gmu}\n"
            f"  Federal opportunities:              {self.federal_count}\n"
            f"  Foundation opportunities:            {self.foundation_count}\n"
            f"  Sources queried:                    {self.sources_queried}\n"
            f"  Sources successful:                 {self.sources_successful}\n"
            f"  Sources failed/skipped:             {self.sources_failed}\n"
            f"  Errors encountered:                 {len(self.errors)}\n"
            f"  Duration:                           {duration}\n"
            f"{'='*60}\n"
        )
