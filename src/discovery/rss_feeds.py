"""RSS feed parser for funding opportunity feeds."""
import logging
from typing import List

import feedparser

from .base import BaseScraper
from ..models import Opportunity, SourceResult

logger = logging.getLogger("geronimo.discovery.rss_feeds")


# Key RSS feeds for funding opportunities
DEFAULT_FEEDS = [
    {
        "name": "Grants.gov - New Opportunities",
        "url": "https://www.grants.gov/rss/GG_NewOppByCategory.xml",
        "funder": "Federal (Various)",
    },
    {
        "name": "Grants.gov - Defense",
        "url": "https://www.grants.gov/rss/GG_OppModByCategory_DOD.xml",
        "funder": "Department of Defense",
    },
    {
        "name": "Grants.gov - State",
        "url": "https://www.grants.gov/rss/GG_OppModByCategory_DOS.xml",
        "funder": "Department of State",
    },
    {
        "name": "Grants.gov - DHS",
        "url": "https://www.grants.gov/rss/GG_OppModByCategory_DHS.xml",
        "funder": "Department of Homeland Security",
    },
    {
        "name": "Grants.gov - NSF",
        "url": "https://www.grants.gov/rss/GG_OppModByCategory_NSF.xml",
        "funder": "National Science Foundation",
    },
]


class RSSFeedScraper(BaseScraper):
    """Scraper that parses RSS feeds for funding opportunities."""

    source_name = "RSS Feeds"

    def search(self, queries: List[str] = None) -> SourceResult:
        """Parse all configured RSS feeds."""
        result = SourceResult(source_name=self.source_name)
        seen_ids = set()
        relevance_keywords = set()
        for q in (queries or []):
            relevance_keywords.update(q.lower().split())

        for feed_config in DEFAULT_FEEDS:
            result.query_count += 1
            try:
                opps = self._parse_feed(feed_config, seen_ids, relevance_keywords)
                result.opportunities.extend(opps)
                result.result_count += len(opps)
            except Exception as e:
                logger.warning(f"RSS feed '{feed_config['name']}' failed: {e}")
                result.errors.append(f"{feed_config['name']}: {e}")

        logger.info(f"RSS Feeds: {result.result_count} from {result.query_count} feeds")
        return result

    def _parse_feed(self, feed_config: dict, seen_ids: set,
                    relevance_kw: set) -> List[Opportunity]:
        """Parse a single RSS feed."""
        opportunities = []

        cached = self.cache.get(feed_config["url"])
        if cached and isinstance(cached, dict) and "entries" in cached:
            entries = cached["entries"]
        else:
            feed = feedparser.parse(feed_config["url"])
            if feed.bozo and not feed.entries:
                logger.warning(f"RSS feed error: {feed_config['name']}")
                return []
            entries = []
            for entry in feed.entries:
                entries.append({
                    "title": getattr(entry, "title", ""),
                    "link": getattr(entry, "link", ""),
                    "summary": getattr(entry, "summary", ""),
                    "published": getattr(entry, "published", ""),
                    "id": getattr(entry, "id", ""),
                })
            self.cache.set(feed_config["url"], {"entries": entries},
                          source=self.source_name)

        for entry in entries:
            entry_id = entry.get("id", entry.get("link", ""))
            if entry_id in seen_ids:
                continue
            seen_ids.add(entry_id)

            title = entry.get("title", "")
            summary = entry.get("summary", "")
            combined = (title + " " + summary).lower()

            # Basic relevance filter for RSS (which can be high-volume)
            if relevance_kw and not any(kw in combined for kw in relevance_kw):
                continue

            opp = self._make_opportunity(
                opportunity_id=entry_id,
                title=title,
                synopsis=summary[:500],
                listing_url=entry.get("link", ""),
                open_date=entry.get("published", ""),
                funder=feed_config.get("funder", ""),
                source_website=feed_config.get("url", ""),
                opportunity_type="Grant",
            )
            opportunities.append(opp)

        return opportunities
