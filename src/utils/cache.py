"""SQLite-based caching for API responses and scraped data."""
import json
import logging
import sqlite3
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("geronimo.cache")


class Cache:
    """Simple SQLite cache for API responses and opportunity data."""

    def __init__(self, db_path: str = "~/agent-geronimo/cache/geronimo_cache.db",
                 ttl_hours: int = 24):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=ttl_hours)
        self._init_db()

    def _init_db(self):
        """Create cache tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS response_cache (
                    cache_key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    source TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS opportunity_cache (
                    opp_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    source TEXT,
                    last_updated TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_expires
                ON response_cache(expires_at)
            """)

    @staticmethod
    def _make_key(url: str, params: dict = None) -> str:
        """Generate a cache key from URL and parameters."""
        key_str = url + (json.dumps(params, sort_keys=True) if params else "")
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(self, url: str, params: dict = None) -> Optional[dict]:
        """Retrieve cached response if not expired."""
        key = self._make_key(url, params)
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT data FROM response_cache WHERE cache_key = ? AND expires_at > ?",
                (key, now),
            ).fetchone()
            if row:
                logger.debug(f"Cache hit for {url}")
                return json.loads(row[0])
        return None

    def set(self, url: str, data: dict, params: dict = None, source: str = ""):
        """Store response in cache."""
        key = self._make_key(url, params)
        now = datetime.utcnow()
        expires = now + self.ttl
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO response_cache
                   (cache_key, data, source, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (key, json.dumps(data), source, now.isoformat(), expires.isoformat()),
            )

    def store_opportunity(self, opp_id: str, data: dict, source: str = ""):
        """Store or update an opportunity record."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO opportunity_cache
                   (opp_id, data, source, last_updated)
                   VALUES (?, ?, ?, ?)""",
                (opp_id, json.dumps(data), source, datetime.utcnow().isoformat()),
            )

    def get_all_opportunities(self) -> list:
        """Retrieve all cached opportunities."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT data FROM opportunity_cache").fetchall()
            return [json.loads(row[0]) for row in rows]

    def clear_expired(self):
        """Remove expired cache entries."""
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            deleted = conn.execute(
                "DELETE FROM response_cache WHERE expires_at <= ?", (now,)
            ).rowcount
            if deleted:
                logger.info(f"Cleared {deleted} expired cache entries")

    def clear_all(self):
        """Clear all cache data."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM response_cache")
            conn.execute("DELETE FROM opportunity_cache")
        logger.info("Cache cleared")
