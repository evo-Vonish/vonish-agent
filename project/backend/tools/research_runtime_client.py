"""Client and lifecycle helpers for the local hollow-search-core runtime."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


class ResearchRuntimeError(RuntimeError):
    """Structured Research Core failure."""

    def __init__(self, code: str, message: str, *, retryable: bool = True, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.detail = detail or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "source": "hollow_search_core",
            "retryable": self.retryable,
            "detail": self.detail,
        }


@dataclass
class StoredResearchContent:
    ref: str
    url: str
    title: str
    content_hash: str
    content: str
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ResearchResultStore:
    """Small in-process result store for web page bodies and evidence material."""

    def __init__(self) -> None:
        self._by_ref: dict[str, StoredResearchContent] = {}
        self._by_url: dict[str, str] = {}
        self._by_hash: dict[str, str] = {}

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

    @staticmethod
    def _summary(text: str, limit: int = 900) -> str:
        compact = " ".join(text.split())
        return compact[:limit] + ("..." if len(compact) > limit else "")

    def put(self, *, url: str, title: str = "", content: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        content = content or ""
        content_hash = self._hash(content)
        existing_ref = self._by_url.get(url) or self._by_hash.get(content_hash)
        if existing_ref and existing_ref in self._by_ref:
            stored = self._by_ref[existing_ref]
            return {
                "duplicate": True,
                "duplicate_of": stored.ref,
                "content_ref": stored.ref,
                "content_hash": stored.content_hash,
                "summary": stored.summary,
            }

        ref = f"research_{content_hash[:16]}"
        stored = StoredResearchContent(
            ref=ref,
            url=url,
            title=title,
            content_hash=content_hash,
            content=content,
            summary=self._summary(content),
            metadata=metadata or {},
        )
        self._by_ref[ref] = stored
        self._by_url[url] = ref
        self._by_hash[content_hash] = ref
        return {
            "duplicate": False,
            "content_ref": ref,
            "content_hash": content_hash,
            "summary": stored.summary,
        }

    def get(self, ref: str) -> StoredResearchContent | None:
        return self._by_ref.get(ref)


_result_store = ResearchResultStore()
_runtime_process: asyncio.subprocess.Process | None = None


def _runtime_path() -> Path:
    return Path(settings.hollow_search_core_path).resolve()


class HollowSearchCoreClient:
    """Async HTTP client for hollow-search-core with auto-start support."""

    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        self.base_url = (base_url or settings.hollow_search_core_url).rstrip("/")
        self.timeout = float(timeout or settings.hollow_search_core_timeout)

    async def ensure_ready(self) -> dict[str, Any]:
        if not settings.hollow_search_core_enabled:
            raise ResearchRuntimeError("RESEARCH_DISABLED", "hollow-search-core is disabled.", retryable=False)

        try:
            health = await self.health()
            if health.get("status") != "ok" or "engines" not in health:
                raise ResearchRuntimeError(
                    "RESEARCH_PORT_CONFLICT",
                    f"{self.base_url} is responding, but it is not hollow-search-core.",
                    detail={"health": health},
                    retryable=False,
                )
            return health
        except ResearchRuntimeError as first_error:
            if not settings.hollow_search_core_auto_start:
                raise first_error
            await start_hollow_search_core()
            deadline = asyncio.get_running_loop().time() + 20
            last_error = first_error
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.5)
                try:
                    health = await self.health()
                    if health.get("status") == "ok" and "engines" in health:
                        return health
                except ResearchRuntimeError as error:
                    last_error = error
            raise ResearchRuntimeError(
                "RESEARCH_START_FAILED",
                f"hollow-search-core did not become healthy: {last_error.message}",
                detail=last_error.detail,
            ) from last_error

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health", timeout=8)

    async def search(self, query: str, mode: str = "overview", max_results: int = 20, language: str | None = None) -> dict[str, Any]:
        await self.ensure_ready()
        payload = {
            "query": query,
            "mode": mode,
            "limit": max(1, min(int(max_results), 50)),
            "language": language or "auto",
        }
        data = await self._request("POST", "/api/search", json_data=payload)
        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("cleanUrl") or item.get("url", ""),
                "snippet": (item.get("content") or item.get("snippet") or "")[:600],
                "engine": item.get("engine", ""),
                "score": item.get("score", 0),
                "domain": item.get("domain", ""),
            }
            for item in data.get("results", [])[: payload["limit"]]
        ]
        return {
            "success": True,
            "query": data.get("query", query),
            "mode": data.get("mode", mode),
            "results": results,
            "dedupe_dropped": data.get("stats", {}).get("duplicatesRemoved", 0),
            "engines": sorted({r["engine"] for r in results if r.get("engine")}),
            "timing_ms": data.get("tookMs", 0),
            "stats": data.get("stats", {}),
        }

    async def fetch(self, url: str, mode: str = "auto", max_chars: int = 20_000) -> dict[str, Any]:
        await self.ensure_ready()
        data = await self._request(
            "POST",
            "/api/fetch",
            json_data={
                "urls": [url],
                "preset": "balanced" if mode == "auto" else mode,
                "maxCharsPerPage": max(500, min(int(max_chars), 100_000)),
                "purify": True,
            },
        )
        pages = data.get("pages", [])
        if not pages:
            return {"success": False, "url": url, "error": "No page returned by Research Core", "stats": data.get("stats", {})}

        page = pages[0]
        text = page.get("text") or page.get("markdown") or ""
        if page.get("status") != "success" or not text.strip():
            return {
                "success": False,
                "url": page.get("url") or url,
                "title": page.get("title", ""),
                "status": page.get("status", "failed"),
                "summary": "",
                "char_count": page.get("charCount", len(text)),
                "error": page.get("error") or "No extracted page text",
                "stats": data.get("stats", {}),
            }
        stored = _result_store.put(
            url=page.get("url") or url,
            title=page.get("title") or "",
            content=text,
            metadata={"status": page.get("status"), "char_count": page.get("charCount", len(text))},
        )
        return {
            "success": page.get("status") == "success",
            "url": page.get("url") or url,
            "title": page.get("title", ""),
            "status": page.get("status", "failed"),
            "summary": stored["summary"],
            "content_ref": stored["content_ref"],
            "content_hash": stored["content_hash"],
            "duplicate": stored["duplicate"],
            "duplicate_of": stored.get("duplicate_of"),
            "char_count": page.get("charCount", len(text)),
            "error": page.get("error"),
            "stats": data.get("stats", {}),
        }

    async def deep_research(
        self,
        query: str,
        mode: str = "deep_dive",
        max_results: int = 15,
        max_pages: int = 8,
        build_evidence: bool = True,
    ) -> dict[str, Any]:
        await self.ensure_ready()
        data = await self._request(
            "POST",
            "/api/research",
            json_data={
                "query": query,
                "mode": mode,
                "searchLimit": max(1, min(int(max_results), 30)),
                "crawlPreset": "balanced",
                "maxEvidencePassages": 30 if build_evidence else 0,
                "supplement": True,
            },
            timeout=max(self.timeout, 180),
        )
        pages = (data.get("crawl") or {}).get("pages", [])[: max(1, min(int(max_pages), 20))]
        content_refs: list[dict[str, Any]] = []
        for page in pages:
            text = page.get("text") or page.get("markdown") or ""
            if not text:
                continue
            stored = _result_store.put(
                url=page.get("url", ""),
                title=page.get("title", ""),
                content=text,
                metadata={"status": page.get("status"), "char_count": page.get("charCount", len(text))},
            )
            content_refs.append(
                {
                    "url": page.get("url", ""),
                    "title": page.get("title", ""),
                    "content_ref": stored["content_ref"],
                    "content_hash": stored["content_hash"],
                    "duplicate": stored["duplicate"],
                    "summary": stored["summary"][:500],
                }
            )

        evidence = data.get("evidence") or {}
        compact_evidence = {
            "passages": [
                {
                    "text": str(p.get("text", ""))[:700],
                    "sourceUrl": p.get("sourceUrl", ""),
                    "sourceTitle": p.get("sourceTitle", ""),
                    "score": p.get("score", 0),
                }
                for p in evidence.get("passages", [])[:12]
            ],
            "claims": evidence.get("claims", [])[:10],
            "gaps": evidence.get("gaps", [])[:8],
            "nextQueries": evidence.get("nextQueries", [])[:8],
            "stats": evidence.get("stats", {}),
        } if evidence else None

        search_results = (data.get("search") or {}).get("results", [])
        return {
            "success": True,
            "query": data.get("query", query),
            "mode": data.get("mode", mode),
            "summary": f"{len(search_results)} results, {len(pages)} pages fetched, {len(content_refs)} content refs, evidence={'ready' if evidence else 'none'}",
            "sources": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("cleanUrl") or r.get("url", ""),
                    "snippet": (r.get("content") or "")[:350],
                    "engine": r.get("engine", ""),
                    "score": r.get("score", 0),
                }
                for r in search_results[: max(1, min(int(max_results), 20))]
            ],
            "evidence_pack": compact_evidence,
            "content_refs": content_refs,
            "stats": {
                "search_ms": (data.get("search") or {}).get("tookMs", 0),
                "crawl_ms": ((data.get("crawl") or {}).get("stats") or {}).get("totalMs", 0),
                "total_ms": data.get("totalMs", 0),
                "total_chars": ((data.get("crawl") or {}).get("stats") or {}).get("totalChars", 0),
            },
            "warnings": [] if evidence else ["Evidence pack was not produced because no successful page had enough text."],
        }

    async def evidence(self, query: str, texts: list[str], max_passages: int = 30) -> dict[str, Any]:
        await self.ensure_ready()
        return await self._request(
            "POST",
            "/api/evidence",
            json_data={"query": query, "texts": texts, "maxPassages": max_passages},
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=timeout or self.timeout, trust_env=False) as client:
                response = await client.request(method, url, json=json_data)
        except httpx.TimeoutException as exc:
            raise ResearchRuntimeError("RESEARCH_TIMEOUT", f"{method} {url} timed out", detail={"url": url}) from exc
        except httpx.ConnectError as exc:
            raise ResearchRuntimeError("RESEARCH_UNAVAILABLE", f"Cannot connect to hollow-search-core at {self.base_url}", detail={"url": self.base_url}) from exc
        except httpx.HTTPError as exc:
            raise ResearchRuntimeError("RESEARCH_HTTP_ERROR", str(exc), detail={"url": url}) from exc

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            code = f"RESEARCH_HTTP_{response.status_code}" if response.status_code >= 400 else "RESEARCH_BAD_JSON"
            raise ResearchRuntimeError(
                code,
                f"hollow-search-core returned non-JSON HTTP {response.status_code}",
                detail={"body": response.text[:1000]},
            ) from exc

        if response.status_code >= 400 or data.get("success") is False or data.get("ok") is False:
            error = data.get("error") if isinstance(data.get("error"), dict) else {}
            message = error.get("message") or data.get("error") or response.reason_phrase
            raise ResearchRuntimeError(
                str(error.get("code") or f"RESEARCH_HTTP_{response.status_code}"),
                str(message),
                retryable=bool(error.get("retryable", error.get("recoverable", True))),
                detail={"status": response.status_code, "response": data},
            )

        return data


async def start_hollow_search_core() -> None:
    global _runtime_process
    if _runtime_process and _runtime_process.returncode is None:
        return

    runtime_dir = _runtime_path()
    entry = runtime_dir / "dist" / "index.js"
    if not entry.exists():
        raise ResearchRuntimeError(
            "RESEARCH_RUNTIME_NOT_BUILT",
            f"hollow-search-core build output not found: {entry}",
            retryable=False,
        )

    parsed = urlparse(settings.hollow_search_core_url)
    env = dict(os.environ)
    if parsed.port:
        env["PORT"] = str(parsed.port)
    logger.info(f"Starting hollow-search-core from {entry}")
    _runtime_process = await asyncio.create_subprocess_exec(
        "node",
        str(entry),
        cwd=str(runtime_dir),
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )


async def shutdown_hollow_search_core() -> None:
    global _runtime_process
    if not _runtime_process or _runtime_process.returncode is not None:
        _runtime_process = None
        return
    _runtime_process.terminate()
    try:
        await asyncio.wait_for(_runtime_process.wait(), timeout=5)
    except asyncio.TimeoutError:
        _runtime_process.kill()
        await _runtime_process.wait()
    _runtime_process = None


def get_research_result_store() -> ResearchResultStore:
    return _result_store
