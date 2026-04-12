#!/usr/bin/env python3
"""
Agent Geronimo — Exhaustive Funding Opportunity Discovery System

A production-ready local agent that searches, aggregates, scores, and exports
funding opportunities relevant to:
  - Taiwan Security Monitor (TSM)
  - George Mason University's Schar School / CSPS
  - National security, defense, intelligence, and policy research centers

Usage:
    python geronimo.py run          # Full pipeline run
    python geronimo.py run --fresh  # Clear cache and run fresh
    python geronimo.py status       # Check last run status
    python geronimo.py clear-cache  # Clear all cached data

Or simply: Run Agent Geronimo
"""
import os
import sys
from pathlib import Path

import click
import yaml
from dotenv import load_dotenv

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logging_config import setup_logging, console
from src.pipeline import Pipeline


def load_config() -> dict:
    """Load settings from YAML config."""
    config_path = PROJECT_ROOT / "config" / "settings.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}


def load_keywords() -> dict:
    """Load keyword configuration."""
    keywords_path = PROJECT_ROOT / "config" / "keywords.yaml"
    if keywords_path.exists():
        with open(keywords_path) as f:
            return yaml.safe_load(f)
    return {}


@click.group()
def cli():
    """Agent Geronimo — Exhaustive Funding Opportunity Discovery System."""
    pass


@cli.command()
@click.option("--fresh", is_flag=True, help="Clear cache before running")
@click.option("--log-level", default="INFO", help="Logging level")
def run(fresh: bool, log_level: str):
    """Execute the full Agent Geronimo pipeline."""
    # Load environment
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    # Setup logging
    logger = setup_logging(
        log_level=log_level,
        log_dir=str(PROJECT_ROOT / "output" / "logs"),
    )

    # Load config
    config = load_config()
    keywords = load_keywords()

    if not keywords:
        console.print("[red]Error: keywords.yaml not found or empty[/red]")
        sys.exit(1)

    # Clear cache if requested
    if fresh:
        from src.utils.cache import Cache
        cache = Cache()
        cache.clear_all()
        console.print("[yellow]Cache cleared — running fresh[/yellow]\n")

    # Run pipeline
    try:
        pipeline = Pipeline(config, keywords)
        excel_path = pipeline.run()
        console.print(f"\n[bold green]✓ Agent Geronimo complete![/bold green]")
        console.print(f"[bold]Output: {excel_path}[/bold]\n")
    except KeyboardInterrupt:
        console.print("\n[yellow]Run interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Pipeline error: {e}[/red]")
        logger.exception("Pipeline failed")
        sys.exit(1)


@cli.command()
def status():
    """Check the last run output."""
    output_dir = Path(PROJECT_ROOT / "output").expanduser()
    if not output_dir.exists():
        console.print("[yellow]No output directory found[/yellow]")
        return

    xlsx_files = sorted(output_dir.glob("Agent_Geronimo_*.xlsx"), reverse=True)
    if xlsx_files:
        latest = xlsx_files[0]
        console.print(f"[green]Latest output:[/green] {latest}")
        console.print(f"[dim]Modified: {latest.stat().st_mtime}[/dim]")
    else:
        console.print("[yellow]No output files found[/yellow]")


@cli.command(name="clear-cache")
def clear_cache():
    """Clear all cached data."""
    from src.utils.cache import Cache
    cache = Cache()
    cache.clear_all()
    console.print("[green]Cache cleared[/green]")


if __name__ == "__main__":
    # Support "python geronimo.py" with no args → default to run
    if len(sys.argv) == 1:
        sys.argv.append("run")
    cli()
