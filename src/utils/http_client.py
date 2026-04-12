"""Rate-limited HTTP client with retry logic and caching."""
import logging
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("geronimo.http")


class RateLimitedClient:
    """HTTP client with rate limiting, retries, and connection pooling."""

    def __init__(
        self,
        rate_limit: float = 2.0,
        timeout: int = 30,
        max_retries: int = 3,
        user_agent: str = "AgentGeronimo/1.0 (Academic Research Funding Discovery)",
    ):
        self.min_interval = 1.0 / rate_limit
        self.timeout = timeout
        self.last_request_time = 0.0

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "application/json, text/html, */*",
        })

        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_maxsize=10)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()

    def get(self, url: str, params: dict = None, headers: dict = None,
            timeout: int = None) -> Optional[requests.Response]:
        """Rate-limited GET request with error handling."""
        self._rate_limit()
        try:
            resp = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout or self.timeout,
            )
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            logger.warning(f"GET {url} failed: {e}")
            return None

    def post(self, url: str, json: dict = None, data: dict = None,
             headers: dict = None, timeout: int = None) -> Optional[requests.Response]:
        """Rate-limited POST request with error handling."""
        self._rate_limit()
        try:
            resp = self.session.post(
                url,
                json=json,
                data=data,
                headers=headers,
                timeout=timeout or self.timeout,
            )
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            logger.warning(f"POST {url} failed: {e}")
            return None

    def get_text(self, url: str, params: dict = None) -> Optional[str]:
        """GET request returning text content."""
        resp = self.get(url, params=params)
        return resp.text if resp else None

    def get_json(self, url: str, params: dict = None) -> Optional[dict]:
        """GET request returning parsed JSON."""
        resp = self.get(url, params=params)
        if resp:
            try:
                return resp.json()
            except ValueError:
                logger.warning(f"Invalid JSON from {url}")
        return None
