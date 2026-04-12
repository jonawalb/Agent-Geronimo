"""Local context integration for TSM pipeline matching.

Reads local files from the TSM!!! folder and other relevant directories
to identify alignment between funding opportunities and existing
TSM concepts, programs, pipelines, and proposal ideas.
"""
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("geronimo.scoring.local_context")


class LocalContextAnalyzer:
    """Analyzes local files to build TSM context for opportunity matching."""

    def __init__(self, tsm_path: str = "~/Desktop/TSM!!!",
                 grants_path: str = "~/Desktop/Grants",
                 scan_extensions: List[str] = None):
        self.tsm_path = Path(tsm_path).expanduser()
        self.grants_path = Path(grants_path).expanduser()
        self.extensions = scan_extensions or [
            ".docx", ".pdf", ".md", ".txt", ".pptx", ".xlsx", ".csv",
        ]
        self.context_themes: List[str] = []
        self.context_projects: List[Dict] = []
        self.context_keywords: set = set()
        self.file_index: Dict[str, str] = {}  # filename -> short description
        self._loaded = False

    def load(self) -> bool:
        """Load and analyze local TSM and grants context."""
        if self._loaded:
            return True

        success = False

        # Load TSM folder
        if self.tsm_path.exists():
            logger.info(f"Loading TSM context from {self.tsm_path}")
            self._scan_directory(self.tsm_path)
            success = True
        else:
            logger.warning(f"TSM path not found: {self.tsm_path}")

        # Load Grants folder
        if self.grants_path.exists():
            logger.info(f"Loading Grants context from {self.grants_path}")
            self._scan_directory(self.grants_path)
            success = True
        else:
            logger.warning(f"Grants path not found: {self.grants_path}")

        if success:
            self._extract_themes()
            self._loaded = True
            logger.info(
                f"Local context loaded: {len(self.file_index)} files, "
                f"{len(self.context_themes)} themes, "
                f"{len(self.context_keywords)} keywords"
            )
        else:
            logger.warning("No local context files accessible")

        return success

    def _scan_directory(self, base_path: Path):
        """Recursively scan directory for relevant files."""
        try:
            for item in base_path.rglob("*"):
                if item.is_file() and item.suffix.lower() in self.extensions:
                    # Skip temp files
                    if item.name.startswith("~$"):
                        continue
                    rel_path = str(item.relative_to(base_path.parent))
                    self.file_index[rel_path] = self._extract_file_info(item)
        except PermissionError as e:
            logger.warning(f"Permission denied scanning {base_path}: {e}")
        except Exception as e:
            logger.warning(f"Error scanning {base_path}: {e}")

    def _extract_file_info(self, filepath: Path) -> str:
        """Extract brief info from a file based on its name and content."""
        name = filepath.stem.replace("_", " ").replace("-", " ")
        info = name

        # For text-based files, try to read a snippet
        if filepath.suffix.lower() in [".md", ".txt", ".csv"]:
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(2000)
                    self.context_keywords.update(
                        self._extract_keywords_from_text(content)
                    )
                    # First meaningful line as description
                    for line in content.split("\n"):
                        line = line.strip()
                        if len(line) > 20 and not line.startswith("#"):
                            info = line[:200]
                            break
            except Exception:
                pass

        elif filepath.suffix.lower() == ".docx":
            try:
                from docx import Document
                doc = Document(str(filepath))
                text = " ".join(p.text for p in doc.paragraphs[:10])
                if text.strip():
                    self.context_keywords.update(
                        self._extract_keywords_from_text(text)
                    )
                    info = text[:200]
            except Exception:
                pass

        # Extract keywords from filename
        self.context_keywords.update(self._extract_keywords_from_text(name))

        return info

    def _extract_keywords_from_text(self, text: str) -> set:
        """Extract security/policy relevant keywords from text."""
        text_lower = text.lower()
        found = set()

        keyword_patterns = [
            "taiwan", "tsm", "monitor", "osint", "geoint", "adiz",
            "narrative warfare", "information warfare", "cognitive warfare",
            "disinformation", "influence", "pla", "prc", "indo-pacific",
            "deterrence", "wargaming", "strategic competition",
            "security", "defense", "intelligence", "cyber",
            "resilience", "policy", "analysis", "briefing",
            "grant", "proposal", "donor", "funding", "pitch",
            "minerva", "smith richardson", "carnegie", "ned",
            "press conference", "early warning", "sentinel",
            "pathfinder", "civil-military", "mobility",
        ]

        for kw in keyword_patterns:
            if kw in text_lower:
                found.add(kw)

        return found

    def _extract_themes(self):
        """Identify recurring themes from scanned files."""
        theme_counts: Dict[str, int] = {}
        theme_map = {
            "Taiwan monitoring & analysis": ["taiwan", "monitor", "tsm", "adiz", "pla"],
            "OSINT / GEOINT": ["osint", "geoint", "geospatial", "satellite", "remote sensing"],
            "Information / narrative warfare": ["narrative warfare", "information warfare",
                                                 "disinformation", "cognitive warfare", "influence"],
            "Strategic competition": ["strategic competition", "great power", "deterrence"],
            "Press monitoring": ["press conference", "press monitor", "mfa"],
            "Early warning / SENTINEL": ["early warning", "sentinel", "warning"],
            "Donor engagement & fundraising": ["donor", "pitch", "funding", "grant", "proposal"],
            "Civil-military analysis": ["civil-military", "mobility", "military"],
            "Wargaming & exercises": ["wargaming", "exercise", "simulation", "tabletop"],
            "Policy research & briefings": ["policy", "briefing", "analysis", "report"],
            "Cyber & tech security": ["cyber", "technology", "ai", "digital"],
        }

        for theme, keywords in theme_map.items():
            count = sum(1 for kw in keywords if kw in self.context_keywords)
            if count > 0:
                theme_counts[theme] = count

        # Sort by count, keep themes with at least 1 match
        self.context_themes = [
            theme for theme, _ in sorted(
                theme_counts.items(), key=lambda x: x[1], reverse=True
            )
        ]

    def match_opportunity(self, opp) -> Tuple[str, str, str, str]:
        """Match an opportunity against local TSM/grants context.

        Returns:
            (pipeline_fit, explanation, concept_match, file_references)
        """
        if not self._loaded:
            return (
                "Local files not accessible",
                "Local files not accessible",
                "",
                "",
            )

        text = (
            opp.title + " " + opp.synopsis + " " + opp.full_description
        ).lower()

        # Find matching themes
        matched_themes = []
        for theme in self.context_themes:
            theme_kw = theme.lower().split()
            if any(kw in text for kw in theme_kw if len(kw) > 3):
                matched_themes.append(theme)

        # Find matching files
        matched_files = []
        for filepath, info in self.file_index.items():
            filepath_lower = filepath.lower()
            info_lower = info.lower()
            # Check if file content/name overlaps with opportunity
            opp_words = set(re.findall(r'\b\w{4,}\b', text))
            file_words = set(re.findall(r'\b\w{4,}\b', filepath_lower + " " + info_lower))
            overlap = opp_words & file_words
            if len(overlap) >= 2:
                matched_files.append(filepath)

        # Generate pipeline fit assessment
        if matched_themes:
            pipeline_fit = "Potential fit with current TSM pipeline"
            explanations = []
            if "Taiwan monitoring & analysis" in matched_themes:
                explanations.append("Matches TSM core monitoring and analytical work")
            if "Information / narrative warfare" in matched_themes:
                explanations.append("Aligns with TSM narrative/information warfare analysis")
            if "OSINT / GEOINT" in matched_themes:
                explanations.append("Could support OSINT/GEOINT mapping and analysis")
            if "Early warning / SENTINEL" in matched_themes:
                explanations.append("Fits SENTINEL early warning system concept")
            if "Press monitoring" in matched_themes:
                explanations.append("Aligns with PRC press monitoring pipeline")
            if "Donor engagement & fundraising" in matched_themes:
                explanations.append("Relates to existing donor/fundraising strategy")
            if "Strategic competition" in matched_themes:
                explanations.append("Fits strategic competition research agenda")
            if "Wargaming & exercises" in matched_themes:
                explanations.append("Could support wargaming/exercise programming")
            if "Policy research & briefings" in matched_themes:
                explanations.append("Aligns with policy briefing and analytical outputs")

            explanation = "; ".join(explanations) if explanations else "; ".join(matched_themes[:3])
        else:
            pipeline_fit = "No direct pipeline match found"
            explanation = "Opportunity may fit broader center programming but no specific TSM pipeline match detected"

        concept_match = "; ".join(matched_themes[:3]) if matched_themes else ""
        file_refs = "; ".join(matched_files[:5]) if matched_files else ""

        return pipeline_fit, explanation, concept_match, file_refs

    def generate_why_column(self, opp) -> str:
        """Generate the 'Why this could work' synthesis column."""
        if not self._loaded:
            return "Local context not available — assess manually against TSM/CSPS priorities"

        pipeline_fit, explanation, _, _ = self.match_opportunity(opp)

        parts = []

        # TSM angle
        if opp.tsm_fit_score >= 50:
            parts.append(f"Strong TSM fit (score: {opp.tsm_fit_score})")
            if explanation and "not accessible" not in explanation:
                parts.append(explanation)
        elif opp.tsm_fit_score >= 30:
            parts.append(f"Moderate TSM fit (score: {opp.tsm_fit_score})")

        # GMU angle
        if opp.gmu_center_fit_score >= 50:
            parts.append(
                f"Strong GMU security center fit (score: {opp.gmu_center_fit_score}) — "
                "viable as Schar School center proposal"
            )

        # Eligibility note
        if any(kw in (opp.eligibility_text or "").lower() for kw in
               ["university", "higher education", "nonprofit", "educational"]):
            parts.append("University/nonprofit eligible")

        # Funder note
        funder_lower = opp.funder.lower() if opp.funder else ""
        if any(f in funder_lower for f in ["smith richardson", "carnegie", "luce", "ned"]):
            parts.append(f"{opp.funder} has history of funding security/policy research")

        # Practical note
        if opp.opportunity_type in ["BAA", "RFP", "Contract"]:
            parts.append("May require teaming with prime contractor or university SPO")
        elif opp.opportunity_type == "Grant":
            parts.append("Standard grant application — manageable for center/PI submission")

        if not parts:
            return "Review for potential alignment with center programming"

        return ". ".join(parts) + "."
