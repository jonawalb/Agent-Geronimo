"""CSV and JSON backup export."""
import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List

from ..models import Opportunity

logger = logging.getLogger("geronimo.export.backup")


def export_csv(opportunities: List[Opportunity], output_dir: str) -> str:
    """Export opportunities to CSV."""
    output_path = Path(output_dir).expanduser()
    output_path.mkdir(parents=True, exist_ok=True)
    filepath = output_path / f"Agent_Geronimo_Results_{datetime.now():%Y_%m_%d}.csv"

    if not opportunities:
        logger.warning("No opportunities to export to CSV")
        return ""

    rows = [opp.to_dict() for opp in opportunities]
    fieldnames = list(rows[0].keys())

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    logger.info(f"CSV export saved: {filepath}")
    return str(filepath)


def export_json(opportunities: List[Opportunity], output_dir: str) -> str:
    """Export opportunities to JSON."""
    output_path = Path(output_dir).expanduser()
    output_path.mkdir(parents=True, exist_ok=True)
    filepath = output_path / f"Agent_Geronimo_Results_{datetime.now():%Y_%m_%d}.json"

    data = {
        "generated": datetime.now().isoformat(),
        "count": len(opportunities),
        "opportunities": [opp.to_dict() for opp in opportunities],
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    logger.info(f"JSON export saved: {filepath}")
    return str(filepath)
