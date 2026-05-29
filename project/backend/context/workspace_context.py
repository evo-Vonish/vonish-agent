"""Workspace Context for Context OS v2.

Manages how workspace files enter the LLM context:
    1. **Working Set** — recently accessed files (with timestamps)
    2. **Pin protection** — pinned files are not compressed during context reduction
    3. **File chunk retrieval** — semantic recall of relevant file chunks
    4. **resource:// URI scheme** — canonical references to workspace resources

Resource URI format::

    resource://workspace/{path}
    resource://workspace/uploads/report.pdf
    resource://workspace/outputs/result.md
    resource://workspace/cache/crawl/result_001.json
    resource://workspace/project/src/main.py#L20-L80
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESOURCE_URI_PATTERN = "resource://workspace/{path}"
_RESOURCE_URI_RE = re.compile(r"^resource://workspace/(.+)$")
_WORKING_SET_MAX_SIZE = 50  # Max files tracked in working set
_PIN_MAX_PER_CONVERSATION = 24  # Max pinned files per conversation


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class WorkingSetEntry(BaseModel):
    """A single entry in the Working Set.

    Tracks when a file was last accessed so compression can protect
    recently-touched files.
    """

    path: str = Field(..., description="Relative path within workspace")
    last_accessed: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = Field(default=1, ge=0, description="Number of times accessed")
    is_pinned: bool = Field(default=False, description="If True, never compress")
    source: str = Field(default="tool_call", description="How the file was accessed")

    @field_validator("path")
    @classmethod
    def _path_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("path must not be empty")
        return v.strip().lstrip("/")

    def touch(self) -> None:
        """Update the last_accessed timestamp and increment access count."""
        self.last_accessed = datetime.now(timezone.utc)
        self.access_count += 1

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "path": self.path,
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "is_pinned": self.is_pinned,
            "source": self.source,
        }


class FileChunk(BaseModel):
    """A chunk of a file retrieved for context injection."""

    source_path: str = Field(..., description="File path this chunk came from")
    content: str = Field(..., description="Chunk text content")
    start_line: int = Field(default=0, ge=0, description="Start line in source file")
    end_line: int = Field(default=0, ge=0, description="End line in source file")
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "content": self.content,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "relevance_score": round(self.relevance_score, 4),
        }


# ---------------------------------------------------------------------------
# Resource URI helpers
# ---------------------------------------------------------------------------


def make_resource_uri(path: str) -> str:
    """Create a canonical resource URI for a workspace path.

    Args:
        path: Relative path within the workspace (e.g. 'uploads/report.pdf').

    Returns:
        resource:// URI string.
    """
    clean_path = path.strip().lstrip("/")
    return f"resource://workspace/{clean_path}"


def parse_resource_uri(uri: str) -> str | None:
    """Parse a resource URI and extract the workspace-relative path.

    Args:
        uri: A resource://workspace/... URI.

    Returns:
        The workspace-relative path, or None if the URI is not a valid
        workspace resource URI.
    """
    match = _RESOURCE_URI_RE.match(uri.strip())
    if match:
        return match.group(1)
    return None


def is_resource_uri(uri: str) -> bool:
    """Check if a string is a valid workspace resource URI.

    Args:
        uri: String to check.

    Returns:
        True if the string matches the resource://workspace/ pattern.
    """
    return _RESOURCE_URI_RE.match(uri.strip()) is not None


def extract_line_range(uri: str) -> tuple[str, int | None, int | None]:
    """Extract path and optional line range from a resource URI.

    Handles URIs like::

        resource://workspace/src/main.py#L20-L80

    Args:
        uri: Resource URI.

    Returns:
        Tuple of (path, start_line, end_line). Lines are None if not specified.
    """
    path = parse_resource_uri(uri) or uri
    start_line: int | None = None
    end_line: int | None = None

    if "#L" in path:
        path_part, range_part = path.split("#L", 1)
        if "-L" in range_part:
            start_str, end_str = range_part.split("-L", 1)
            try:
                start_line = int(start_str)
                end_line = int(end_str)
            except ValueError:
                pass
        else:
            try:
                start_line = int(range_part)
                end_line = start_line
            except ValueError:
                pass
        path = path_part

    return path, start_line, end_line


# ---------------------------------------------------------------------------
# Workspace Context
# ---------------------------------------------------------------------------


class WorkspaceContext:
    """Manages workspace file context for a conversation.

    Per-conversation working-set tracking, pin protection, and file chunk
    retrieval. All state is indexed by *conversation_id*.
    """

    def __init__(self) -> None:
        """Initialize with empty state."""
        # conversation_id -> {path: WorkingSetEntry}
        self._working_sets: dict[str, dict[str, WorkingSetEntry]] = {}
        # conversation_id -> {path: pinned_boolean}
        self._pins: dict[str, set[str]] = {}
        # Simple in-memory chunk cache: (conversation_id, path, query) -> [FileChunk]
        self._chunk_cache: dict[tuple[str, str, str], list[FileChunk]] = {}

    # -- Working Set Management ----------------------------------------

    def touch_file(
        self,
        conversation_id: str,
        path: str,
        source: str = "tool_call",
    ) -> WorkingSetEntry:
        """Record that a file was accessed (adds to Working Set).

        Args:
            conversation_id: Conversation ID.
            path: Workspace-relative file path.
            source: How the file was accessed (e.g. 'tool_call', 'upload', 'user').

        Returns:
            The WorkingSetEntry (new or updated).
        """
        ws = self._get_or_create_ws(conversation_id)
        clean_path = path.strip().lstrip("/")

        if clean_path in ws:
            entry = ws[clean_path]
            entry.touch()
            entry.source = source
        else:
            # Evict oldest if at capacity
            if len(ws) >= _WORKING_SET_MAX_SIZE:
                self._evict_oldest(conversation_id)

            entry = WorkingSetEntry(path=clean_path, source=source)
            ws[clean_path] = entry

        return entry

    def get_working_set(
        self,
        conversation_id: str,
        limit: int | None = None,
        include_pinned_first: bool = True,
    ) -> list[WorkingSetEntry]:
        """Get the Working Set for a conversation.

        Args:
            conversation_id: Conversation ID.
            limit: Maximum entries to return. None = all.
            include_pinned_first: If True, pinned entries appear first.

        Returns:
            List of WorkingSetEntry, most-recently-accessed first.
        """
        ws = self._working_sets.get(conversation_id, {})
        entries = list(ws.values())

        # Sort: pinned first, then by last_accessed descending
        if include_pinned_first:
            entries.sort(key=lambda e: (not e.is_pinned, e.last_accessed), reverse=False)
            # Reverse the time sort within each pin group
            pinned = [e for e in entries if e.is_pinned]
            unpinned = [e for e in entries if not e.is_pinned]
            pinned.sort(key=lambda e: e.last_accessed, reverse=True)
            unpinned.sort(key=lambda e: e.last_accessed, reverse=True)
            entries = pinned + unpinned
        else:
            entries.sort(key=lambda e: e.last_accessed, reverse=True)

        if limit:
            entries = entries[:limit]
        return entries

    def get_working_set_paths(self, conversation_id: str) -> list[str]:
        """Get just the paths from the Working Set.

        Args:
            conversation_id: Conversation ID.

        Returns:
            List of workspace-relative paths.
        """
        return [e.path for e in self.get_working_set(conversation_id)]

    def is_in_working_set(self, conversation_id: str, path: str) -> bool:
        """Check if a path is in the Working Set.

        Args:
            conversation_id: Conversation ID.
            path: Workspace-relative path.

        Returns:
            True if the path is tracked.
        """
        ws = self._working_sets.get(conversation_id, {})
        return path.strip().lstrip("/") in ws

    # -- Pin Protection ------------------------------------------------

    def pin_file(self, conversation_id: str, path: str) -> bool:
        """Pin a file to protect it from compression.

        Pinned files are treated as sacred: their content is never
        summarised or reference-ised during context compaction.

        Args:
            conversation_id: Conversation ID.
            path: Workspace-relative file path.

        Returns:
            True if the file was pinned, False if at pin limit.
        """
        pins = self._pins.setdefault(conversation_id, set())
        if len(pins) >= _PIN_MAX_PER_CONVERSATION and path not in pins:
            logger.warning(
                "Pin limit reached for conversation",
                extra={"conversation_id": conversation_id, "limit": _PIN_MAX_PER_CONVERSATION},
            )
            return False

        clean_path = path.strip().lstrip("/")
        pins.add(clean_path)

        # Also ensure it's in the working set
        ws = self._get_or_create_ws(conversation_id)
        if clean_path in ws:
            ws[clean_path].is_pinned = True
        else:
            ws[clean_path] = WorkingSetEntry(path=clean_path, is_pinned=True, source="manual_pin")

        return True

    def unpin_file(self, conversation_id: str, path: str) -> bool:
        """Unpin a file, allowing it to be compressed.

        Args:
            conversation_id: Conversation ID.
            path: Workspace-relative file path.

        Returns:
            True if the file was previously pinned and is now unpinned.
        """
        pins = self._pins.get(conversation_id, set())
        clean_path = path.strip().lstrip("/")
        was_pinned = clean_path in pins

        if was_pinned:
            pins.discard(clean_path)
            ws = self._working_sets.get(conversation_id, {})
            if clean_path in ws:
                ws[clean_path].is_pinned = False

        return was_pinned

    def is_pinned(self, conversation_id: str, path: str) -> bool:
        """Check if a file is pinned.

        Args:
            conversation_id: Conversation ID.
            path: Workspace-relative file path.

        Returns:
            True if the file is pinned.
        """
        pins = self._pins.get(conversation_id, set())
        return path.strip().lstrip("/") in pins

    def get_pinned_files(self, conversation_id: str) -> list[str]:
        """Get all pinned file paths for a conversation.

        Args:
            conversation_id: Conversation ID.

        Returns:
            List of pinned workspace-relative paths.
        """
        return sorted(self._pins.get(conversation_id, set()))

    # -- File Chunk Retrieval ------------------------------------------

    async def get_file_chunks(
        self,
        conversation_id: str,
        query: str,
        top_k: int = 8,
    ) -> list[FileChunk]:
        """Retrieve relevant file chunks for a query.

        This is a simplified implementation that returns chunks based on:
        1. Files in the Working Set
        2. Keyword matching against the query

        In production, this should integrate with a vector database for
        semantic similarity search.

        Args:
            conversation_id: Conversation ID.
            query: User query string for relevance ranking.
            top_k: Maximum chunks to return.

        Returns:
            List of FileChunk instances, sorted by relevance.
        """
        ws_entries = self.get_working_set(conversation_id, limit=top_k * 2)
        if not ws_entries:
            return []

        chunks: list[FileChunk] = []
        query_lower = query.lower()
        query_terms = set(query_lower.split())

        for entry in ws_entries:
            # Skip entries that are not actual files
            if entry.source not in ("tool_call", "upload", "user"):
                continue

            # Try to read the file and extract relevant chunks
            file_chunks = self._extract_file_chunks(
                entry.path, query_terms, top_k=3
            )
            chunks.extend(file_chunks)

        # Sort by relevance score
        chunks.sort(key=lambda c: c.relevance_score, reverse=True)
        return chunks[:top_k]

    def _extract_file_chunks(
        self,
        path: str,
        query_terms: set[str],
        top_k: int = 3,
    ) -> list[FileChunk]:
        """Extract relevant chunks from a single file.

        Simplified implementation: reads the file, splits into logical
        chunks, and scores by keyword overlap.

        Args:
            path: Workspace-relative file path.
            query_terms: Lowercase query terms for scoring.
            top_k: Max chunks per file.

        Returns:
            List of FileChunk instances.
        """
        # NOTE: In production, this would read from the actual workspace
        # filesystem or database. For now, we return placeholder chunks
        # that can be overridden by a real implementation.
        uri = make_resource_uri(path)

        # Try to read the actual file from workspace
        try:
            from core.config import settings
            full_path = settings.workspace_root / path
            if full_path.exists():
                content = full_path.read_text(encoding="utf-8", errors="replace")
                return self._chunk_content(path, content, query_terms, top_k)
        except Exception:
            pass

        # Fallback: return a placeholder chunk referencing the file
        return [
            FileChunk(
                source_path=path,
                content=f"[File: {path}]\n{uri}",
                relevance_score=0.5,
            )
        ]

    def _chunk_content(
        self,
        path: str,
        content: str,
        query_terms: set[str],
        top_k: int,
    ) -> list[FileChunk]:
        """Split content into chunks and score by keyword overlap.

        Args:
            path: File path for chunk attribution.
            content: Full file content.
            query_terms: Query terms for scoring.
            top_k: Maximum chunks.

        Returns:
            Scored FileChunk list.
        """
        lines = content.split("\n")
        chunk_size = 50  # lines per chunk
        overlap = 10  # line overlap between chunks

        chunks: list[FileChunk] = []
        i = 0
        while i < len(lines):
            end = min(i + chunk_size, len(lines))
            chunk_lines = lines[i:end]
            chunk_text = "\n".join(chunk_lines)

            # Score by term overlap
            chunk_lower = chunk_text.lower()
            matches = sum(1 for term in query_terms if term in chunk_lower)
            score = min(1.0, matches / max(1, len(query_terms)) * 0.8 + 0.1)

            # Boost score for code definitions, function signatures
            if any(line.strip().startswith(("def ", "class ", "async def")) for line in chunk_lines):
                score = min(1.0, score + 0.1)

            chunks.append(FileChunk(
                source_path=path,
                content=chunk_text,
                start_line=i + 1,
                end_line=end,
                relevance_score=score,
            ))

            if end >= len(lines):
                break
            i += chunk_size - overlap

        chunks.sort(key=lambda c: c.relevance_score, reverse=True)
        return chunks[:top_k]

    # -- Context Building ----------------------------------------------

    def build_workspace_refs(
        self,
        conversation_id: str,
        profile,
        include_chunks: bool = True,
    ) -> str:
        """Build a text block of workspace references for context injection.

        Args:
            conversation_id: Conversation ID.
            profile: ContextProfile (for workspace_chunk_top_k and formatting).
            include_chunks: Whether to include file chunk summaries.

        Returns:
            Formatted text block for the system prompt or message context.
        """
        from context.context_profile import ContextProfile

        if not isinstance(profile, ContextProfile):
            raise TypeError(f"profile must be ContextProfile, got {type(profile).__name__}")

        ws_entries = self.get_working_set(conversation_id, limit=profile.workspace_chunk_top_k * 2)
        if not ws_entries:
            return ""

        lines: list[str] = ["## Workspace Files"]

        for entry in ws_entries[:profile.workspace_chunk_top_k * 2]:
            uri = make_resource_uri(entry.path)
            pin_marker = " [PINNED]" if entry.is_pinned else ""
            lines.append(f"- {entry.path}{pin_marker} — {uri}")

        return "\n".join(lines)

    def build_workspace_chunks_text(
        self,
        conversation_id: str,
        query: str,
        profile,
    ) -> str:
        """Build a text block of relevant file chunks for context injection.

        Args:
            conversation_id: Conversation ID.
            query: Query for chunk relevance.
            profile: ContextProfile with workspace_chunk_top_k.

        Returns:
            Formatted text block of relevant chunks.
        """
        from context.context_profile import ContextProfile

        if not isinstance(profile, ContextProfile):
            raise TypeError(f"profile must be ContextProfile, got {type(profile).__name__}")

        # Use cached chunks if available
        cache_key = (conversation_id, query)
        cached = self._chunk_cache.get((conversation_id, "__all__", query))
        if cached is not None:
            chunks = cached
        else:
            # Note: get_file_chunks is async, but this method is sync.
            # Callers should use this method from an async context or
            # pre-fetch chunks. We return a placeholder here.
            chunks = []

        if not chunks:
            return ""

        lines: list[str] = [f"## Relevant File Chunks ({len(chunks)} chunks)"]
        for chunk in chunks[:profile.workspace_chunk_top_k]:
            lines.append(f"### {chunk.source_path} (L{chunk.start_line}-L{chunk.end_line})")
            lines.append(chunk.content)
            lines.append("")

        return "\n".join(lines)

    # -- Internal helpers ----------------------------------------------

    def _get_or_create_ws(self, conversation_id: str) -> dict[str, WorkingSetEntry]:
        """Get or create a working set for a conversation."""
        if conversation_id not in self._working_sets:
            self._working_sets[conversation_id] = {}
        return self._working_sets[conversation_id]

    def _evict_oldest(self, conversation_id: str) -> None:
        """Evict the oldest unpinned entry from the working set."""
        ws = self._working_sets.get(conversation_id, {})
        if not ws:
            return

        # Find oldest unpinned entry
        oldest: WorkingSetEntry | None = None
        oldest_path: str | None = None

        for path, entry in ws.items():
            if entry.is_pinned:
                continue
            if oldest is None or entry.last_accessed < oldest.last_accessed:
                oldest = entry
                oldest_path = path

        if oldest_path:
            del ws[oldest_path]
            logger.debug(
                "Evicted oldest working set entry",
                extra={"conversation_id": conversation_id, "path": oldest_path},
            )

    def clear_conversation(self, conversation_id: str) -> None:
        """Clear all workspace context for a conversation.

        Args:
            conversation_id: Conversation ID to clear.
        """
        self._working_sets.pop(conversation_id, None)
        self._pins.pop(conversation_id, None)

        # Clear chunk cache entries for this conversation
        keys_to_remove = [
            k for k in self._chunk_cache if k[0] == conversation_id
        ]
        for k in keys_to_remove:
            self._chunk_cache.pop(k, None)

        logger.debug(
            "Cleared workspace context",
            extra={"conversation_id": conversation_id},
        )


# ---------------------------------------------------------------------------
# Global instance
# ---------------------------------------------------------------------------

_workspace_context: WorkspaceContext | None = None


def get_workspace_context() -> WorkspaceContext:
    """Get the global WorkspaceContext instance."""
    global _workspace_context
    if _workspace_context is None:
        _workspace_context = WorkspaceContext()
    return _workspace_context
