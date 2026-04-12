"""Main pipeline orchestrator for Agent Geronimo.

Coordinates the full 6-stage retrieval pipeline:
  Stage 1: Broad discovery (APIs, scrapers, RSS, web search)
  Stage 2: Deep enrichment (detail fetching, portal discovery)
  Stage 3: Relevance scoring (TSM, GMU, general security)
  Stage 4: Historical award context (funder intelligence)
  Stage 5: Local alignment (TSM files, pipeline matching)
  Stage 6: Export (Excel, CSV, JSON, Markdown)
"""
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict

import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.panel import Panel
from rich.table import Table

from .models import Opportunity, RunStats
from .utils.http_client import RateLimitedClient
from .utils.cache import Cache
from .discovery.grants_gov import GrantsGovScraper
from .discovery.sam_gov import SamGovScraper
from .discovery.usaspending import USASpendingScraper
from .discovery.web_search import WebSearchScraper
from .discovery.rss_feeds import RSSFeedScraper
from .enrichment.detail_fetcher import DetailFetcher
from .enrichment.award_analyzer import AwardAnalyzer
from .scoring.relevance import score_opportunity
from .scoring.local_context import LocalContextAnalyzer
from .dedup.deduplicator import Deduplicator
from .export.excel_writer import ExcelWriter
from .export.csv_json_writer import export_csv, export_json
from .export.markdown_writer import export_markdown

logger = logging.getLogger("geronimo.pipeline")
console = Console()


class Pipeline:
    """Main Agent Geronimo pipeline orchestrator."""

    def __init__(self, config: dict, keywords: dict):
        self.config = config
        self.keywords = keywords
        self.stats = RunStats()

        # Initialize shared components
        scrape_cfg = config.get("scraping", {})
        self.client = RateLimitedClient(
            rate_limit=scrape_cfg.get("rate_limit_per_second", 2),
            timeout=scrape_cfg.get("request_timeout", 30),
            max_retries=scrape_cfg.get("retry_attempts", 3),
            user_agent=scrape_cfg.get("user_agent",
                                       "AgentGeronimo/1.0"),
        )

        cache_cfg = config.get("cache", {})
        self.cache = Cache(
            db_path=cache_cfg.get("database", "~/agent-geronimo/cache/geronimo_cache.db"),
            ttl_hours=cache_cfg.get("ttl_hours", 24),
        )

        # Build search queries from keywords config
        self.search_queries = self._build_queries()

    def run(self) -> str:
        """Execute the full pipeline. Returns path to Excel output."""
        console.print(Panel(
            "[bold cyan]AGENT GERONIMO[/bold cyan]\n"
            "[dim]Exhaustive Funding Opportunity Discovery System[/dim]",
            border_style="cyan",
        ))
        console.print()

        self.stats.start_time = datetime.now()
        all_opportunities: List[Opportunity] = []

        # ── Stage 1: Broad Discovery ──
        console.print("[bold]Stage 1/6: Broad Discovery[/bold]")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("Querying sources...", total=5)

            # Grants.gov
            progress.update(task, description="[cyan]Grants.gov API...")
            try:
                scraper = GrantsGovScraper(self.client, self.cache, self.keywords)
                result = scraper.search(self.search_queries.get("grants_gov", []))
                all_opportunities.extend(result.opportunities)
                self.stats.sources_queried += 1
                self.stats.sources_successful += 1
                console.print(f"  Grants.gov: [green]{result.result_count}[/green] opportunities")
            except Exception as e:
                self.stats.sources_failed += 1
                self.stats.errors.append(f"Grants.gov: {e}")
                console.print(f"  Grants.gov: [red]Failed[/red] - {e}")
            progress.advance(task)

            # SAM.gov
            progress.update(task, description="[cyan]SAM.gov API...")
            try:
                scraper = SamGovScraper(self.client, self.cache, self.keywords)
                result = scraper.search(self.search_queries.get("sam_gov", []))
                all_opportunities.extend(result.opportunities)
                self.stats.sources_queried += 1
                self.stats.sources_successful += 1
                console.print(f"  SAM.gov: [green]{result.result_count}[/green] opportunities")
            except Exception as e:
                self.stats.sources_failed += 1
                self.stats.errors.append(f"SAM.gov: {e}")
                console.print(f"  SAM.gov: [red]Failed[/red] - {e}")
            progress.advance(task)

            # RSS Feeds
            progress.update(task, description="[cyan]RSS Feeds...")
            try:
                scraper = RSSFeedScraper(self.client, self.cache, self.keywords)
                result = scraper.search(self._flat_keywords())
                all_opportunities.extend(result.opportunities)
                self.stats.sources_queried += 1
                self.stats.sources_successful += 1
                console.print(f"  RSS Feeds: [green]{result.result_count}[/green] opportunities")
            except Exception as e:
                self.stats.sources_failed += 1
                self.stats.errors.append(f"RSS: {e}")
                console.print(f"  RSS Feeds: [red]Failed[/red] - {e}")
            progress.advance(task)

            # Web Search / Site Scraping
            progress.update(task, description="[cyan]Web Search & Site Scraping...")
            try:
                scraper = WebSearchScraper(self.client, self.cache, self.keywords)
                result = scraper.search(self._flat_keywords())
                all_opportunities.extend(result.opportunities)
                self.stats.sources_queried += 1
                self.stats.sources_successful += 1
                console.print(f"  Web Search: [green]{result.result_count}[/green] opportunities")
            except Exception as e:
                self.stats.sources_failed += 1
                self.stats.errors.append(f"Web Search: {e}")
                console.print(f"  Web Search: [red]Failed[/red] - {e}")
            progress.advance(task)

            # USAspending (past awards)
            progress.update(task, description="[cyan]USAspending (past awards)...")
            try:
                scraper = USASpendingScraper(self.client, self.cache, self.keywords)
                result = scraper.search(self._flat_keywords()[:10])
                self.stats.sources_queried += 1
                self.stats.sources_successful += 1
                console.print(f"  USAspending: [green]{result.result_count}[/green] past awards indexed")
            except Exception as e:
                self.stats.sources_failed += 1
                self.stats.errors.append(f"USAspending: {e}")
            progress.advance(task)

        self.stats.total_raw = len(all_opportunities)
        console.print(f"\n  [bold]Raw opportunities: {self.stats.total_raw}[/bold]\n")

        # ── Stage 2: Deduplication ──
        console.print("[bold]Stage 2/6: Deduplication[/bold]")
        deduper = Deduplicator(
            title_threshold=self.config.get("deduplication", {}).get(
                "title_similarity_threshold", 85
            )
        )
        opportunities = deduper.deduplicate(all_opportunities)
        self.stats.total_deduped = len(opportunities)
        console.print(
            f"  Deduplicated: {self.stats.total_raw} → "
            f"[green]{self.stats.total_deduped}[/green] unique\n"
        )

        # ── Stage 3: Enrichment ──
        console.print("[bold]Stage 3/6: Detail Enrichment[/bold]")
        detail_fetcher = DetailFetcher(self.client)
        enriched = 0
        # Only enrich high-potential opportunities (top 100 by title keyword match)
        to_enrich = opportunities[:100] if len(opportunities) > 100 else opportunities
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("Enriching details...", total=len(to_enrich))
            for opp in to_enrich:
                try:
                    detail_fetcher.enrich(opp)
                    enriched += 1
                except Exception:
                    pass
                progress.advance(task)
        console.print(f"  Enriched {enriched} opportunities\n")

        # ── Stage 4: Scoring & Funder Intelligence ──
        console.print("[bold]Stage 4/6: Relevance Scoring & Funder Intelligence[/bold]")
        award_analyzer = AwardAnalyzer(self.client, self.cache)
        for opp in opportunities:
            score_opportunity(opp)
            award_analyzer.enrich_with_funder_intelligence(opp)

        # Sort by overall score
        opportunities.sort(key=lambda o: o.overall_relevance_score, reverse=True)

        # Count categories
        self.stats.high_priority_tsm = sum(1 for o in opportunities if o.tsm_fit_score >= 20)
        self.stats.high_priority_gmu = sum(1 for o in opportunities if o.gmu_center_fit_score >= 20)
        self.stats.federal_count = sum(1 for o in opportunities
                                       if o.opportunity_type in ["Grant", "Contract", "BAA", "RFP"])
        self.stats.foundation_count = sum(1 for o in opportunities
                                          if any(kw in (o.funder or "").lower()
                                                for kw in ["foundation", "endowment", "fund"]))

        console.print(f"  TSM high-priority: [green]{self.stats.high_priority_tsm}[/green]")
        console.print(f"  GMU high-priority: [green]{self.stats.high_priority_gmu}[/green]\n")

        # ── Stage 5: Local Context Alignment ──
        console.print("[bold]Stage 5/6: Local Context Alignment[/bold]")
        local_cfg = self.config.get("local_context", {})
        local_analyzer = LocalContextAnalyzer(
            tsm_path=local_cfg.get("tsm_path", "~/Desktop/TSM!!!"),
            grants_path=local_cfg.get("grants_path", "~/Desktop/Grants"),
            scan_extensions=local_cfg.get("scan_extensions"),
        )

        if local_analyzer.load():
            console.print("  [green]Local context loaded[/green]")
            for opp in opportunities:
                fit, explanation, concept, files = local_analyzer.match_opportunity(opp)
                opp.tsm_pipeline_fit = fit
                opp.tsm_pipeline_explanation = explanation
                opp.existing_concept_match = concept
                opp.internal_file_references = files
                opp.why_this_could_work = local_analyzer.generate_why_column(opp)
        else:
            console.print("  [yellow]Local files not accessible — skipping pipeline match[/yellow]")
            for opp in opportunities:
                opp.tsm_pipeline_fit = "Local files not accessible"
                opp.why_this_could_work = (
                    f"Score: TSM={opp.tsm_fit_score}, GMU={opp.gmu_center_fit_score}. "
                    "Manual review recommended against TSM/CSPS priorities."
                )
        console.print()

        # ── Stage 6: Export ──
        console.print("[bold]Stage 6/6: Export[/bold]")
        self.stats.end_time = datetime.now()

        output_cfg = self.config.get("output", {})
        output_dir = output_cfg.get("directory", "~/agent-geronimo/output")

        # Excel (primary)
        excel_writer = ExcelWriter(output_dir=output_dir)
        excel_path = excel_writer.export(opportunities, self.stats)
        console.print(f"  Excel: [green]{excel_path}[/green]")

        # CSV backup
        if output_cfg.get("also_export_csv", True):
            csv_path = export_csv(opportunities, output_dir)
            if csv_path:
                console.print(f"  CSV:   [green]{csv_path}[/green]")

        # JSON backup
        if output_cfg.get("also_export_json", True):
            json_path = export_json(opportunities, output_dir)
            if json_path:
                console.print(f"  JSON:  [green]{json_path}[/green]")

        # Markdown summary
        if output_cfg.get("also_export_markdown", True):
            md_path = export_markdown(opportunities, self.stats, output_dir)
            if md_path:
                console.print(f"  MD:    [green]{md_path}[/green]")

        # Print summary
        console.print(self.stats.summary())

        # Top opportunities table
        self._print_top_table(opportunities)

        return excel_path

    def _build_queries(self) -> Dict[str, List[str]]:
        """Build search queries from keywords config."""
        search_queries = self.keywords.get("search_queries", {})
        return {
            "grants_gov": search_queries.get("grants_gov", []),
            "sam_gov": search_queries.get("sam_gov", []),
            "foundation": search_queries.get("foundation", []),
        }

    def _flat_keywords(self) -> List[str]:
        """Get a flat list of primary keywords for general searches."""
        primary = self.keywords.get("primary_keywords", {})
        flat = []
        for category_keywords in primary.values():
            flat.extend(category_keywords)
        return flat

    def _print_top_table(self, opportunities: List[Opportunity]):
        """Print a summary table of top opportunities."""
        table = Table(title="Top 15 Opportunities by Overall Score")
        table.add_column("Score", style="bold", width=6)
        table.add_column("TSM", width=5)
        table.add_column("GMU", width=5)
        table.add_column("Title", width=45)
        table.add_column("Funder", width=22)
        table.add_column("Type", width=10)
        table.add_column("Rec", width=10)

        for opp in opportunities[:15]:
            score_style = "green" if opp.overall_relevance_score >= 60 else (
                "yellow" if opp.overall_relevance_score >= 35 else "dim"
            )
            table.add_row(
                str(opp.overall_relevance_score),
                str(opp.tsm_fit_score),
                str(opp.gmu_center_fit_score),
                opp.title[:45],
                opp.funder[:22],
                opp.opportunity_type[:10],
                opp.final_recommendation,
                style=score_style,
            )

        console.print(table)
        console.print()
