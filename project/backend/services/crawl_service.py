"""Crawl service for the Agent system.

Fetches and extracts content from web URLs.
"""

from __future__ import annotations

import time
from pydantic import BaseModel, Field
from typing import Any

import httpx

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class CrawlResult(BaseModel):
    """Result of crawling a URL."""

    url: str
    title: str
    content: str
    content_type: str
    links: list[str] = Field(default_factory=list)
    fetch_time_ms: float = 0.0
    status_code: int = 200
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "content_preview": self.content[:500] if self.content else "",
            "content_type": self.content_type,
            "links_count": len(self.links),
            "fetch_time_ms": self.fetch_time_ms,
            "status_code": self.status_code,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Crawl Service
# ---------------------------------------------------------------------------


class CrawlService:
    """Service for fetching and extracting web content.

    Features:
    - HTML content extraction (article mode)
    - Markdown conversion
    - Link extraction
    - Timeout and error handling
    - Content length limiting
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._max_content_length = 50_000  # characters

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; AgentBot/1.0)"
                },
            )
        return self._client

    async def fetch(
        self,
        url: str,
        extract_type: str = "article",
        max_length: int | None = None,
        timeout: int = 30,
    ) -> CrawlResult:
        """Fetch and extract content from a URL.

        Args:
            url: URL to fetch.
            extract_type: Extraction type (text, markdown, html, article).
            max_length: Maximum content length.
            timeout: Request timeout in seconds.

        Returns:
            CrawlResult with extracted content.
        """
        max_len = max_length or self._max_content_length
        start_time = time.monotonic()

        try:
            client = await self._get_client()

            response = await client.get(url, timeout=timeout)
            status_code = response.status_code

            if status_code != 200:
                elapsed = (time.monotonic() - start_time) * 1000
                return CrawlResult(
                    url=url,
                    title="",
                    content="",
                    content_type="",
                    fetch_time_ms=elapsed,
                    status_code=status_code,
                    error=f"HTTP {status_code}",
                )

            content_type = response.headers.get("content-type", "")
            html_content = response.text

            # Extract content based on type
            if extract_type == "article":
                title, content, links = self._extract_article(html_content, url)
            elif extract_type == "markdown":
                title, content, links = self._extract_markdown(html_content, url)
            elif extract_type == "text":
                title, content, links = self._extract_text(html_content, url)
            else:
                title, content, links = self._extract_html(html_content, url)

            # Truncate if needed
            if len(content) > max_len:
                content = content[:max_len] + "\n\n[Content truncated due to length]"

            elapsed = (time.monotonic() - start_time) * 1000

            return CrawlResult(
                url=url,
                title=title,
                content=content,
                content_type=content_type,
                links=links[:50],  # Limit links
                fetch_time_ms=elapsed,
                status_code=status_code,
            )

        except httpx.TimeoutException:
            elapsed = (time.monotonic() - start_time) * 1000
            return CrawlResult(
                url=url,
                title="",
                content="",
                content_type="",
                fetch_time_ms=elapsed,
                status_code=0,
                error="Request timeout",
            )

        except Exception as e:
            elapsed = (time.monotonic() - start_time) * 1000
            logger.error(f"Crawl error for {url}: {e}")
            return CrawlResult(
                url=url,
                title="",
                content="",
                content_type="",
                fetch_time_ms=elapsed,
                status_code=0,
                error=str(e),
            )

    def _extract_article(
        self, html: str, url: str
    ) -> tuple[str, str, list[str]]:
        """Extract article content from HTML.

        Uses BeautifulSoup to extract main article content.
        """
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")

            # Remove script and style elements
            for script in soup(["script", "style", "nav", "header", "footer"]):
                script.decompose()

            # Try to find main content
            title = ""
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text(strip=True)

            h1 = soup.find("h1")
            if h1 and not title:
                title = h1.get_text(strip=True)

            # Look for article or main content
            article = soup.find("article") or soup.find("main") or soup.find("body")

            if article:
                # Extract paragraphs
                paragraphs = article.find_all(["p", "h1", "h2", "h3", "h4", "li"])
                content = "\n\n".join(
                    p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
                )
            else:
                content = soup.get_text(separator="\n", strip=True)

            # Extract links
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("http"):
                    links.append(href)

            return title, content, links

        except ImportError:
            return self._extract_text(html, url)

    def _extract_markdown(
        self, html: str, url: str
    ) -> tuple[str, str, list[str]]:
        """Convert HTML to Markdown.

        Placeholder: Returns text extraction.
        Full implementation would use html2text or similar.
        """
        title, content, links = self._extract_article(html, url)
        return title, content, links

    def _extract_text(self, html: str, url: str) -> tuple[str, str, list[str]]:
        """Extract plain text from HTML."""
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")

            for script in soup(["script", "style"]):
                script.decompose()

            title = ""
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text(strip=True)

            text = soup.get_text(separator="\n", strip=True)

            links = [
                a["href"] for a in soup.find_all("a", href=True)
                if a["href"].startswith("http")
            ]

            return title, text, links

        except ImportError:
            # Fallback: strip HTML tags with regex
            import re

            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            return "", text, []

    def _extract_html(self, html: str, url: str) -> tuple[str, str, list[str]]:
        """Return raw HTML."""
        return "", html, []

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# ---------------------------------------------------------------------------
# Global Instance
# ---------------------------------------------------------------------------

_crawl_service: CrawlService | None = None


def get_crawl_service() -> CrawlService:
    """Get the global crawl service instance."""
    global _crawl_service
    if _crawl_service is None:
        _crawl_service = CrawlService()
    return _crawl_service
