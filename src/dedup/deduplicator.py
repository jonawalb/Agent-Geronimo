"""Aggressive deduplication for funding opportunities.

Uses multiple strategies:
1. Exact match on opportunity ID + funder
2. Normalized title similarity (fuzzy matching)
3. URL pattern matching
4. Deadline + funder combination
"""
import logging
import re
from typing import List, Dict, Tuple

from rapidfuzz import fuzz

from ..models import Opportunity

logger = logging.getLogger("geronimo.dedup")


class Deduplicator:
    """Deduplicate opportunities using multi-strategy matching."""

    def __init__(self, title_threshold: int = 85):
        self.title_threshold = title_threshold

    def deduplicate(self, opportunities: List[Opportunity]) -> List[Opportunity]:
        """Remove duplicate opportunities, preserving source provenance."""
        if not opportunities:
            return []

        logger.info(f"Deduplicating {len(opportunities)} raw opportunities...")

        # Index by multiple keys
        by_id: Dict[str, List[int]] = {}
        by_url: Dict[str, List[int]] = {}
        by_title_funder: Dict[str, List[int]] = {}

        for idx, opp in enumerate(opportunities):
            # Key 1: Opportunity ID
            if opp.opportunity_id:
                key = self._normalize(opp.opportunity_id)
                by_id.setdefault(key, []).append(idx)

            # Key 2: URL
            if opp.listing_url:
                url_key = self._normalize_url(opp.listing_url)
                by_url.setdefault(url_key, []).append(idx)

            # Key 3: Title + Funder (normalized)
            title_key = self._normalize(opp.title) + "|" + self._normalize(opp.funder)
            by_title_funder.setdefault(title_key, []).append(idx)

        # Build merge groups
        merged = set()  # indices to skip
        kept = []  # final deduplicated list

        for idx, opp in enumerate(opportunities):
            if idx in merged:
                continue

            # Find all duplicates of this opportunity
            dup_indices = {idx}

            # Check ID matches
            if opp.opportunity_id:
                key = self._normalize(opp.opportunity_id)
                dup_indices.update(by_id.get(key, []))

            # Check URL matches
            if opp.listing_url:
                url_key = self._normalize_url(opp.listing_url)
                dup_indices.update(by_url.get(url_key, []))

            # Check title+funder matches
            title_key = self._normalize(opp.title) + "|" + self._normalize(opp.funder)
            dup_indices.update(by_title_funder.get(title_key, []))

            # Fuzzy title matching against remaining unmerged
            for other_idx in range(idx + 1, len(opportunities)):
                if other_idx in merged:
                    continue
                other = opportunities[other_idx]
                if self._is_fuzzy_match(opp, other):
                    dup_indices.add(other_idx)

            # Merge: keep the most complete record
            if len(dup_indices) > 1:
                best_idx = self._select_best(opportunities, dup_indices)
                best_opp = opportunities[best_idx]

                # Collect all source URLs from duplicates
                all_urls = set()
                all_sources = set()
                for di in dup_indices:
                    d = opportunities[di]
                    if d.listing_url:
                        all_urls.add(d.listing_url)
                    if d.source_name:
                        all_sources.add(d.source_name)

                best_opp.all_source_urls = "; ".join(all_urls)
                if len(all_sources) > 1:
                    best_opp.notes = (
                        (best_opp.notes or "") +
                        f" [Found on: {', '.join(all_sources)}]"
                    ).strip()

                merged.update(dup_indices - {best_idx})
                kept.append(best_opp)
            else:
                kept.append(opp)

            merged.update(dup_indices)

        removed = len(opportunities) - len(kept)
        logger.info(f"Deduplication complete: {len(kept)} unique ({removed} duplicates removed)")
        return kept

    def _is_fuzzy_match(self, a: Opportunity, b: Opportunity) -> bool:
        """Check if two opportunities are fuzzy duplicates."""
        if not a.title or not b.title:
            return False

        # Quick check: same funder?
        if a.funder and b.funder:
            funder_sim = fuzz.ratio(
                self._normalize(a.funder),
                self._normalize(b.funder),
            )
            if funder_sim < 50:
                return False  # Different funders, probably not duplicates

        # Title similarity
        title_sim = fuzz.ratio(
            self._normalize(a.title),
            self._normalize(b.title),
        )
        if title_sim >= self.title_threshold:
            return True

        # Token sort ratio (handles word reordering)
        token_sim = fuzz.token_sort_ratio(
            self._normalize(a.title),
            self._normalize(b.title),
        )
        if token_sim >= 90:
            return True

        return False

    def _select_best(self, opportunities: List[Opportunity],
                     indices: set) -> int:
        """Select the most complete opportunity record from duplicates."""
        best_idx = min(indices)
        best_score = 0

        for idx in indices:
            opp = opportunities[idx]
            score = 0
            if opp.synopsis:
                score += 3
            if opp.full_description:
                score += 3
            if opp.deadline:
                score += 2
            if opp.listing_url:
                score += 2
            if opp.application_url:
                score += 2
            if opp.award_min or opp.award_max:
                score += 2
            if opp.eligibility_text:
                score += 2
            if opp.funder:
                score += 1
            # Prefer official sources
            if "grants.gov" in (opp.source_website or "").lower():
                score += 3
            if "sam.gov" in (opp.source_website or "").lower():
                score += 3

            if score > best_score:
                best_score = score
                best_idx = idx

        return best_idx

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize text for comparison."""
        if not text:
            return ""
        return re.sub(r'[^a-z0-9\s]', '', text.lower().strip())

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize URL for comparison."""
        if not url:
            return ""
        url = url.lower().strip().rstrip("/")
        url = re.sub(r'^https?://(www\.)?', '', url)
        url = re.sub(r'[?#].*$', '', url)
        return url
