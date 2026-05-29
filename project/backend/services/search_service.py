"""Search service for the Agent system.

Provides web search capabilities using various search engines.
"""

from __future__ import annotations

import urllib.parse
from pydantic import BaseModel, Field
from typing import Any

import httpx

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class SearchResult(BaseModel):
    """A single search result."""

    title: str
    url: str
    snippet: str
    source: str = ""
    published_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source,
            "published_date": self.published_date,
        }


class SearchResponse(BaseModel):
    """Response from a search query."""

    query: str
    results: list[SearchResult]
    total_results: int = 0
    search_time_ms: float = 0.0
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "results": [r.to_dict() for r in self.results],
            "total_results": self.total_results,
            "search_time_ms": self.search_time_ms,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# Search Service
# ---------------------------------------------------------------------------


class SearchService:
    """Service for web search operations.

    Supports multiple search backends:
    - DuckDuckGo (default, no API key required)
    - Bing (API key required)
    - Serper/Google (API key required)
    """

    def __init__(self, backend: str = "duckduckgo") -> None:
        self.backend = backend
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
            )
        return self._client

    async def search(
        self,
        query: str,
        num_results: int = 5,
        source: str = "general",
    ) -> SearchResponse:
        """Execute a web search.

        Args:
            query: Search query string.
            num_results: Number of results to return.
            source: Search source type (general, news, academic).

        Returns:
            SearchResponse with results.
        """
        import time

        start_time = time.monotonic()

        if self.backend == "duckduckgo":
            results = await self._search_duckduckgo(query, num_results)
        elif self.backend == "bing":
            results = await self._search_bing(query, num_results)
        else:
            results = await self._search_mock(query, num_results)

        elapsed = (time.monotonic() - start_time) * 1000

        return SearchResponse(
            query=query,
            results=results,
            total_results=len(results),
            search_time_ms=elapsed,
            source=self.backend,
        )

    async def _search_duckduckgo(
        self, query: str, num_results: int
    ) -> list[SearchResult]:
        """Search using DuckDuckGo.

        Uses DuckDuckGo's HTML interface for lightweight searching.
        """
        try:
            client = await self._get_client()

            # DuckDuckGo lite search
            params = {
                "q": query,
                "kl": "us-en",
            }

            response = await client.get(
                "https://duckduckgo.com/html/",
                params=params,
            )

            if response.status_code != 200:
                logger.warning(f"DuckDuckGo search failed: {response.status_code}")
                return []

            # Parse HTML results
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(response.text, "html.parser")
            results: list[SearchResult] = []

            for result in soup.select(".result"):
                title_elem = result.select_one(".result__title")
                snippet_elem = result.select_one(".result__snippet")
                url_elem = result.select_one(".result__url")

                if title_elem and snippet_elem:
                    title = title_elem.get_text(strip=True)
                    snippet = snippet_elem.get_text(strip=True)
                    url = url_elem.get_text(strip=True) if url_elem else ""

                    # Get href from title link
                    link = title_elem.find("a")
                    if link and link.get("href"):
                        url = link["href"]

                    results.append(
                        SearchResult(
                            title=title,
                            url=url,
                            snippet=snippet,
                            source="duckduckgo",
                        )
                    )

                    if len(results) >= num_results:
                        break

            return results

        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            return []

    async def _search_bing(self, query: str, num_results: int) -> list[SearchResult]:
        """Search using Bing API.

        Requires BING_API_KEY environment variable.
        """
        import os

        api_key = os.environ.get("BING_API_KEY", "")
        if not api_key:
            logger.warning("BING_API_KEY not set, using mock results")
            return await self._search_mock(query, num_results)

        try:
            client = await self._get_client()

            response = await client.get(
                "https://api.bing.microsoft.com/v7.0/search",
                headers={"Ocp-Apim-Subscription-Key": api_key},
                params={"q": query, "count": num_results},
            )
            response.raise_for_status()
            data = response.json()

            results: list[SearchResult] = []
            for item in data.get("webPages", {}).get("value", []):
                results.append(
                    SearchResult(
                        title=item.get("name", ""),
                        url=item.get("url", ""),
                        snippet=item.get("snippet", ""),
                        source="bing",
                    )
                )

            return results

        except Exception as e:
            logger.error(f"Bing search error: {e}")
            return await self._search_mock(query, num_results)

    async def _search_mock(self, query: str, num_results: int) -> list[SearchResult]:
        """Return mock search results for development."""
        logger.info(f"Mock search for: {query}")

        encoded = urllib.parse.quote(query)
        return [
            SearchResult(
                title=f"Result {i + 1} for '{query}'",
                url=f"https://example.com/search?{encoded}&page={i + 1}",
                snippet=f"This is a mock search result snippet for '{query}'. "
                f"In production, this will contain actual search results from the web.",
                source="mock",
            )
            for i in range(min(num_results, 3))
        ]

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# ---------------------------------------------------------------------------
# Global Instance
# ---------------------------------------------------------------------------

_search_service: SearchService | None = None


def get_search_service() -> SearchService:
    """Get the global search service instance."""
    global _search_service
    if _search_service is None:
        _search_service = SearchService()
    return _search_service
