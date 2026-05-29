"""Workspace file indexer.

Manages .workspace/index.json for fast file search and metadata tracking
without requiring filesystem walks.
"""

from __future__ import annotations

import json
import fnmatch
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiofiles
from pydantic import BaseModel, Field

from workspace.permissions import PathSandbox, SecurityError
from workspace.storage_provider import FileInfo
from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class IndexEntry(BaseModel):
    """Single entry in the workspace index."""

    path: str
    name: str
    size: int
    mime_type: str
    is_directory: bool
    modified_at: str  # ISO format
    created_at: str | None = None  # ISO format
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_file_info(cls, file_info: FileInfo) -> IndexEntry:
        return cls(
            path=file_info.path,
            name=file_info.name,
            size=file_info.size,
            mime_type=file_info.mime_type,
            is_directory=file_info.is_directory,
            modified_at=(
                file_info.modified_at.isoformat()
                if file_info.modified_at
                else datetime.now(timezone.utc).isoformat()
            ),
            created_at=(
                file_info.created_at.isoformat() if file_info.created_at else None
            ),
            metadata=file_info.metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "size": self.size,
            "mime_type": self.mime_type,
            "is_directory": self.is_directory,
            "modified_at": self.modified_at,
            "created_at": self.created_at,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IndexEntry:
        return cls(
            path=data["path"],
            name=data["name"],
            size=data["size"],
            mime_type=data.get("mime_type", "application/octet-stream"),
            is_directory=data.get("is_directory", False),
            modified_at=data["modified_at"],
            created_at=data.get("created_at"),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Workspace Indexer
# ---------------------------------------------------------------------------


class WorkspaceIndexer:
    """Manages .workspace/index.json file index for fast searching.

    The index provides:
    - Fast file search without filesystem walks
    - Metadata tracking for each file
    - Tag-based organization
    - Full-text search on filenames and paths

    Index structure:
        {
            "version": 1,
            "updated_at": "2024-01-01T00:00:00+00:00",
            "entries": {
                "path/to/file.txt": IndexEntry,
                ...
            }
        }
    """

    INDEX_VERSION = 1
    INDEX_FILE = ".workspace/index.json"

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self._index_path = self.workspace_root / self.INDEX_FILE
        self._sandbox = PathSandbox(self.workspace_root)
        self._cache: dict[str, IndexEntry] | None = None

    @property
    def _index_dir(self) -> Path:
        return self._index_path.parent

    async def _ensure_index_dir(self) -> None:
        """Ensure the .workspace directory exists."""
        self._index_dir.mkdir(parents=True, exist_ok=True)

    async def _load_index(self) -> dict[str, IndexEntry]:
        """Load index from disk.

        Returns:
            Dictionary of path -> IndexEntry.
        """
        if self._cache is not None:
            return self._cache

        if not self._index_path.exists():
            self._cache = {}
            return self._cache

        try:
            async with aiofiles.open(self._index_path, "r", encoding="utf-8") as f:
                content = await f.read()

            data = json.loads(content)
            entries = {
                path: IndexEntry.from_dict(entry_data)
                for path, entry_data in data.get("entries", {}).items()
            }
            self._cache = entries
            return entries
        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning(f"Failed to load index, starting fresh: {e}")
            self._cache = {}
            return self._cache

    async def _save_index(self, entries: dict[str, IndexEntry]) -> None:
        """Save index to disk.

        Args:
            entries: Dictionary of path -> IndexEntry.
        """
        await self._ensure_index_dir()

        data = {
            "version": self.INDEX_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entry_count": len(entries),
            "entries": {
                path: entry.to_dict() for path, entry in entries.items()
            },
        }

        async with aiofiles.open(self._index_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=2, default=str))

        self._cache = entries
        logger.debug(f"Saved index with {len(entries)} entries")

    async def add_file(
        self, workspace_id: str, file_info: FileInfo, tags: list[str] | None = None
    ) -> None:
        """Add or update a file in the index.

        Args:
            workspace_id: Workspace identifier.
            file_info: File information to index.
            tags: Optional tags to associate with the file.
        """
        entries = await self._load_index()

        entry = IndexEntry.from_file_info(file_info)
        if tags:
            entry.tags = tags

        entries[file_info.path] = entry
        await self._save_index(entries)

        logger.debug(f"Indexed file: {file_info.path}")

    async def remove_file(self, workspace_id: str, path: str) -> bool:
        """Remove a file from the index.

        Args:
            workspace_id: Workspace identifier.
            path: Relative file path.

        Returns:
            True if file was in index and removed.
        """
        entries = await self._load_index()

        if path not in entries:
            return False

        del entries[path]
        await self._save_index(entries)

        logger.debug(f"Removed from index: {path}")
        return True

    async def update_file(
        self,
        workspace_id: str,
        file_info: FileInfo,
        tags: list[str] | None = None,
    ) -> None:
        """Update a file's index entry.

        Convenience method that is equivalent to add_file (upsert).

        Args:
            workspace_id: Workspace identifier.
            file_info: Updated file information.
            tags: Optional tags to update.
        """
        await self.add_file(workspace_id, file_info, tags)

    async def get_index(self, workspace_id: str) -> dict[str, Any]:
        """Get the full index as a dictionary.

        Args:
            workspace_id: Workspace identifier.

        Returns:
            Index dictionary with version, timestamp, and entries.
        """
        entries = await self._load_index()

        return {
            "version": self.INDEX_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entry_count": len(entries),
            "entries": {path: entry.to_dict() for path, entry in entries.items()},
        }

    async def search_index(
        self,
        workspace_id: str,
        query: str,
        search_content: bool = False,
    ) -> list[FileInfo]:
        """Search the file index.

        Performs case-insensitive search on file names and paths.
        Supports glob patterns (e.g., "*.py", "uploads/*").

        Args:
            workspace_id: Workspace identifier.
            query: Search query string.
            search_content: Whether to search in tags and metadata too.

        Returns:
            List of matching FileInfo objects, sorted by relevance.
        """
        entries = await self._load_index()

        if not query:
            return [
                self._entry_to_file_info(entry)
                for entry in entries.values()
            ]

        query_lower = query.lower()
        is_glob = any(c in query for c in "*?[]")

        matches: list[tuple[int, FileInfo]] = []

        for entry in entries.values():
            score = 0
            name_lower = entry.name.lower()
            path_lower = entry.path.lower()

            if is_glob:
                # Glob pattern matching
                if fnmatch.fnmatch(name_lower, query_lower) or fnmatch.fnmatch(
                    path_lower, query_lower
                ):
                    score = 100
            else:
                # Substring matching with scoring
                if query_lower == name_lower:
                    score = 1000  # Exact name match
                elif query_lower in name_lower:
                    score = 500  # Name contains query
                elif query_lower in path_lower:
                    score = 300  # Path contains query
                elif query_lower in entry.mime_type.lower():
                    score = 100  # MIME type match

                if search_content:
                    # Search tags
                    for tag in entry.tags:
                        if query_lower in tag.lower():
                            score = max(score, 200)

                    # Search metadata values
                    for key, value in entry.metadata.items():
                        if query_lower in str(key).lower() or query_lower in str(
                            value
                        ).lower():
                            score = max(score, 150)

            if score > 0:
                matches.append((score, self._entry_to_file_info(entry)))

        # Sort by score descending
        matches.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in matches]

    async def get_file_tags(self, workspace_id: str, path: str) -> list[str]:
        """Get tags for a file.

        Args:
            workspace_id: Workspace identifier.
            path: Relative file path.

        Returns:
            List of tags, empty if file not in index.
        """
        entries = await self._load_index()

        if path not in entries:
            return []

        return list(entries[path].tags)

    async def set_file_tags(
        self, workspace_id: str, path: str, tags: list[str]
    ) -> None:
        """Set tags for a file.

        Args:
            workspace_id: Workspace identifier.
            path: Relative file path.
            tags: Tags to set.
        """
        entries = await self._load_index()

        if path not in entries:
            logger.warning(f"Cannot set tags for unindexed file: {path}")
            return

        entries[path].tags = tags
        await self._save_index(entries)

    async def rebuild_index(
        self,
        workspace_id: str,
        list_files_func,
    ) -> dict[str, Any]:
        """Rebuild the entire index from filesystem.

        Args:
            workspace_id: Workspace identifier.
            list_files_func: Async callable -> list[FileInfo].

        Returns:
            Statistics about the rebuild.
        """
        await self._ensure_index_dir()

        try:
            files = await list_files_func()
        except Exception as e:
            logger.error(f"Failed to list files for index rebuild: {e}")
            return {"success": False, "error": str(e), "indexed": 0}

        new_entries: dict[str, IndexEntry] = {}

        for file_info in files:
            entry = IndexEntry.from_file_info(file_info)
            new_entries[file_info.path] = entry

        await self._save_index(new_entries)

        stats = {
            "success": True,
            "indexed": len(new_entries),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(f"Rebuilt index for workspace {workspace_id}: {stats['indexed']} files")
        return stats

    async def get_stats(self, workspace_id: str) -> dict[str, Any]:
        """Get index statistics.

        Args:
            workspace_id: Workspace identifier.

        Returns:
            Statistics dictionary.
        """
        entries = await self._load_index()

        total_size = sum(e.size for e in entries.values() if not e.is_directory)
        file_count = sum(1 for e in entries.values() if not e.is_directory)
        dir_count = sum(1 for e in entries.values() if e.is_directory)

        mime_types: dict[str, int] = {}
        for e in entries.values():
            mime_types[e.mime_type] = mime_types.get(e.mime_type, 0) + 1

        return {
            "total_entries": len(entries),
            "file_count": file_count,
            "directory_count": dir_count,
            "total_size": total_size,
            "mime_type_breakdown": mime_types,
        }

    def _entry_to_file_info(self, entry: IndexEntry) -> FileInfo:
        """Convert an IndexEntry to FileInfo.

        Args:
            entry: Index entry.

        Returns:
            FileInfo object.
        """
        modified_at = None
        created_at = None

        try:
            modified_at = datetime.fromisoformat(entry.modified_at)
        except ValueError:
            pass

        if entry.created_at:
            try:
                created_at = datetime.fromisoformat(entry.created_at)
            except ValueError:
                pass

        return FileInfo(
            name=entry.name,
            path=entry.path,
            size=entry.size,
            mime_type=entry.mime_type,
            is_directory=entry.is_directory,
            modified_at=modified_at,
            created_at=created_at,
            metadata=entry.metadata,
        )
