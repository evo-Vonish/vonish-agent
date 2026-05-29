"""Server Storage Provider for Workspace system.

Implements StorageProvider for server-side storage.
Currently uses local filesystem as a simulation of remote server storage,
with a clear migration path to S3/cloud storage in the future.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

import aiofiles
import aiofiles.os

from workspace.permissions import PathSandbox, SecurityError
from workspace.storage_provider import FileInfo, StorageProvider, StorageStats
from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# MIME Type Detection (shared)
# ---------------------------------------------------------------------------

MIME_TYPES: dict[str, str] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".py": "text/x-python",
    ".js": "text/javascript",
    ".ts": "text/x-typescript",
    ".html": "text/html",
    ".css": "text/css",
    ".json": "application/json",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".xml": "text/xml",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".zip": "application/zip",
    ".tar": "application/x-tar",
    ".gz": "application/gzip",
    ".bz2": "application/x-bzip2",
    ".7z": "application/x-7z-compressed",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
}

# Maximum file size: 50MB
MAX_FILE_SIZE = 50 * 1024 * 1024


def guess_mime_type(filename: str) -> str:
    """Guess MIME type from filename extension."""
    ext = Path(filename).suffix.lower()
    return MIME_TYPES.get(ext, "application/octet-stream")


# ---------------------------------------------------------------------------
# Server Storage Provider (Local FS Simulation)
# ---------------------------------------------------------------------------


class ServerStorageProvider(StorageProvider):
    """Server-side storage provider using local filesystem as simulation.

    This provider mirrors the LocalStorageProvider interface but operates
    on a separate root directory, simulating remote server storage.

    Migration path to S3:
    1. Override _read_raw, _write_raw, _delete_raw, _list_raw methods
    2. Use boto3/aiobotocore for S3 operations
    3. Keep the same public interface - no changes needed to callers

    Attributes:
        server_root: Root directory for server storage simulation.
        workspace_id: Current workspace identifier for path prefixing.
    """

    def __init__(
        self,
        server_root: str | Path = "",
        workspace_id: str = "",
        max_size: int = 1024 * 1024 * 1024,  # 1GB default
    ) -> None:
        """Initialize server storage provider.

        Args:
            server_root: Root directory for server storage. If empty,
                        uses WORKSPACE_ROOT from settings.
            workspace_id: Workspace identifier for path prefixing.
            max_size: Maximum storage size in bytes.
        """
        if not server_root:
            from core.config import settings

            server_root = settings.workspace_root + "_server"

        self.server_root = Path(server_root).resolve()
        self.server_root.mkdir(parents=True, exist_ok=True)
        self.workspace_id = workspace_id
        self._max_size = max_size
        self._sandbox = PathSandbox(self.server_root)

        # Metadata cache for simulating remote metadata
        self._metadata_cache: dict[str, dict[str, Any]] = {}

    def _resolve_path(self, path: str) -> Path:
        """Resolve a workspace-relative path to server storage path.

        Args:
            path: Relative path within workspace.

        Returns:
            Absolute path in server storage.

        Raises:
            SecurityError: If path is invalid.
        """
        return self._sandbox.validate_path(path)

    def _resolve_create_path(self, path: str) -> Path:
        """Resolve a path for creation in server storage.

        Args:
            path: Relative path within workspace.

        Returns:
            Absolute path in server storage.

        Raises:
            SecurityError: If path is invalid.
        """
        return self._sandbox.validate_create_path(path)

    def _get_relative(self, full_path: Path) -> str:
        """Get relative path from server root."""
        return self._sandbox.get_relative_path(full_path)

    # -- StorageProvider interface ------------------------------------------

    async def read_file(self, path: str) -> bytes:
        """Read a file from server storage.

        Args:
            path: Relative path within workspace.

        Returns:
            File contents as bytes.

        Raises:
            FileNotFoundError: If file does not exist.
            SecurityError: If path is invalid.
        """
        safe_path = self._resolve_path(path)

        if not safe_path.exists():
            raise FileNotFoundError(f"File not found in server storage: {path}")

        if not safe_path.is_file():
            raise ValueError(f"Path is not a file: {path}")

        async with aiofiles.open(safe_path, "rb") as f:
            data = await f.read()

        logger.debug(f"Server storage read: {path} ({len(data)} bytes)")
        return data

    async def write_file(self, path: str, data: bytes) -> None:
        """Write a file to server storage.

        Args:
            path: Relative path within workspace.
            data: File contents as bytes.

        Raises:
            SecurityError: If path is invalid.
            ValueError: If file exceeds size limit.
        """
        safe_path = self._resolve_create_path(path)

        if len(data) > MAX_FILE_SIZE:
            raise ValueError(
                f"File size {len(data)} exceeds maximum of {MAX_FILE_SIZE} bytes"
            )

        # Create parent directories
        safe_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(safe_path, "wb") as f:
            await f.write(data)

        # Update metadata cache
        self._metadata_cache[str(safe_path)] = {
            "size": len(data),
            "modified_at": datetime.now(timezone.utc).isoformat(),
            "content_hash": hashlib.sha256(data).hexdigest(),
        }

        logger.debug(f"Server storage write: {path} ({len(data)} bytes)")

    async def delete_file(self, path: str) -> None:
        """Delete a file from server storage.

        Args:
            path: Relative path within workspace.

        Raises:
            FileNotFoundError: If file does not exist.
            SecurityError: If path is invalid.
        """
        safe_path = self._resolve_path(path)

        if not safe_path.exists():
            raise FileNotFoundError(f"File not found in server storage: {path}")

        if not safe_path.is_file():
            raise ValueError(f"Path is not a file: {path}")

        await aiofiles.os.remove(safe_path)
        self._metadata_cache.pop(str(safe_path), None)
        logger.debug(f"Server storage delete: {path}")

    async def list_files(
        self, path: str = "", recursive: bool = False
    ) -> list[FileInfo]:
        """List files in server storage.

        Args:
            path: Relative directory path (empty for root).
            recursive: Whether to list recursively.

        Returns:
            List of FileInfo objects.
        """
        if path:
            safe_path = self._resolve_path(path)
        else:
            safe_path = self.server_root

        if not safe_path.exists():
            return []

        if not safe_path.is_dir():
            stat = safe_path.stat()
            rel_path = self._get_relative(safe_path)
            return [
                FileInfo(
                    name=safe_path.name,
                    path=rel_path,
                    size=stat.st_size,
                    mime_type=guess_mime_type(safe_path.name),
                    is_directory=False,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    created_at=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
                )
            ]

        result: list[FileInfo] = []

        if recursive:
            for root, dirs, files in os.walk(safe_path):
                root_path = Path(root)
                for d in dirs:
                    if d.startswith(".") and d != ".workspace":
                        continue
                    dir_path = root_path / d
                    stat = dir_path.stat()
                    rel_path = self._get_relative(dir_path)
                    result.append(
                        FileInfo(
                            name=d,
                            path=rel_path,
                            size=0,
                            mime_type="directory",
                            is_directory=True,
                            modified_at=datetime.fromtimestamp(
                                stat.st_mtime, tz=timezone.utc
                            ),
                        )
                    )
                for f in files:
                    if f.startswith("."):
                        continue
                    file_path = root_path / f
                    stat = file_path.stat()
                    rel_path = self._get_relative(file_path)
                    result.append(
                        FileInfo(
                            name=f,
                            path=rel_path,
                            size=stat.st_size,
                            mime_type=guess_mime_type(f),
                            is_directory=False,
                            modified_at=datetime.fromtimestamp(
                                stat.st_mtime, tz=timezone.utc
                            ),
                            created_at=datetime.fromtimestamp(
                                stat.st_ctime, tz=timezone.utc
                            ),
                        )
                    )
        else:
            for entry in os.scandir(safe_path):
                if entry.name.startswith(".") and entry.name != ".workspace":
                    continue
                stat = entry.stat()
                rel_path = self._get_relative(Path(entry.path))
                result.append(
                    FileInfo(
                        name=entry.name,
                        path=rel_path,
                        size=stat.st_size if entry.is_file() else 0,
                        mime_type="directory"
                        if entry.is_dir()
                        else guess_mime_type(entry.name),
                        is_directory=entry.is_dir(),
                        modified_at=datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ),
                        created_at=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)
                        if entry.is_file()
                        else None,
                    )
                )

        return result

    async def file_exists(self, path: str) -> bool:
        """Check if a file exists in server storage.

        Args:
            path: Relative path within workspace.

        Returns:
            True if file exists.
        """
        try:
            safe_path = self._resolve_path(path)
            return safe_path.exists()
        except (SecurityError, OSError):
            return False

    async def get_file_info(self, path: str) -> FileInfo | None:
        """Get file information from server storage.

        Args:
            path: Relative path within workspace.

        Returns:
            FileInfo or None if file does not exist.
        """
        try:
            safe_path = self._resolve_path(path)

            if not safe_path.exists():
                return None

            stat = safe_path.stat()
            rel_path = self._get_relative(safe_path)

            return FileInfo(
                name=safe_path.name,
                path=rel_path,
                size=stat.st_size if safe_path.is_file() else 0,
                mime_type="directory"
                if safe_path.is_dir()
                else guess_mime_type(safe_path.name),
                is_directory=safe_path.is_dir(),
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                created_at=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
            )
        except (SecurityError, OSError):
            return None

    async def create_directory(self, path: str) -> None:
        """Create a directory in server storage.

        Args:
            path: Relative directory path.
        """
        safe_path = self._resolve_create_path(path)
        safe_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Server storage create directory: {path}")

    async def delete_directory(self, path: str, recursive: bool = False) -> None:
        """Delete a directory from server storage.

        Args:
            path: Relative directory path.
            recursive: Whether to delete contents recursively.
        """
        safe_path = self._resolve_path(path)

        if not safe_path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")

        if not safe_path.is_dir():
            raise ValueError(f"Path is not a directory: {path}")

        if recursive:
            await aiofiles.os.wrap(shutil.rmtree)(safe_path)
        else:
            await aiofiles.os.rmdir(safe_path)

        logger.debug(f"Server storage delete directory: {path}")

    async def move_file(self, source: str, destination: str) -> None:
        """Move a file in server storage.

        Args:
            source: Source relative path.
            destination: Destination relative path.
        """
        safe_source = self._resolve_path(source)
        safe_dest = self._resolve_create_path(destination)

        if not safe_source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        safe_dest.parent.mkdir(parents=True, exist_ok=True)
        await aiofiles.os.wrap(shutil.move)(str(safe_source), str(safe_dest))

        # Update metadata cache
        src_key = str(safe_source)
        dst_key = str(safe_dest)
        if src_key in self._metadata_cache:
            self._metadata_cache[dst_key] = self._metadata_cache.pop(src_key)

        logger.debug(f"Server storage move: {source} -> {destination}")

    async def copy_file(self, source: str, destination: str) -> None:
        """Copy a file in server storage.

        Args:
            source: Source relative path.
            destination: Destination relative path.
        """
        safe_source = self._resolve_path(source)
        safe_dest = self._resolve_create_path(destination)

        if not safe_source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        safe_dest.parent.mkdir(parents=True, exist_ok=True)
        await aiofiles.os.wrap(shutil.copy2)(str(safe_source), str(safe_dest))

        # Copy metadata cache entry
        src_key = str(safe_source)
        dst_key = str(safe_dest)
        if src_key in self._metadata_cache:
            self._metadata_cache[dst_key] = dict(self._metadata_cache[src_key])

        logger.debug(f"Server storage copy: {source} -> {destination}")

    async def get_stats(self) -> StorageStats:
        """Get storage statistics.

        Returns:
            StorageStats with usage information.
        """
        total_size = 0
        total_files = 0

        for root, _, files in os.walk(self.server_root):
            for f in files:
                if f.startswith("."):
                    continue
                file_path = Path(root) / f
                try:
                    total_size += file_path.stat().st_size
                    total_files += 1
                except OSError:
                    pass

        return StorageStats(
            total_files=total_files,
            total_size=total_size,
            max_size=self._max_size,
            available_size=max(0, self._max_size - total_size),
        )

    async def stream_file(self, path: str) -> AsyncGenerator[bytes, None]:
        """Stream a file from server storage.

        Args:
            path: Relative path within workspace.

        Yields:
            File content chunks (64KB each).
        """
        safe_path = self._resolve_path(path)

        if not safe_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        chunk_size = 64 * 1024
        async with aiofiles.open(safe_path, "rb") as f:
            while True:
                chunk = await f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    # -- Migration helpers for S3/cloud -------------------------------------

    async def get_content_hash(self, path: str) -> str | None:
        """Get SHA-256 content hash of a file.

        This is useful for comparing files between local and server storage.

        Args:
            path: Relative path within workspace.

        Returns:
            SHA-256 hex digest or None if file doesn't exist.
        """
        try:
            safe_path = self._resolve_path(path)
            cache_key = str(safe_path)

            # Check cache first
            if cache_key in self._metadata_cache:
                return self._metadata_cache[cache_key].get("content_hash")

            # Compute hash from file content
            if not safe_path.exists():
                return None

            async with aiofiles.open(safe_path, "rb") as f:
                data = await f.read()

            content_hash = hashlib.sha256(data).hexdigest()
            self._metadata_cache[cache_key] = {
                "size": len(data),
                "modified_at": datetime.now(timezone.utc).isoformat(),
                "content_hash": content_hash,
            }
            return content_hash
        except (SecurityError, OSError):
            return None

    async def sync_from_local(
        self, local_root: Path, paths: list[str] | None = None
    ) -> dict[str, Any]:
        """Synchronize files from local storage to server storage.

        This is a batch operation for syncing local changes to server.

        Args:
            local_root: Root path of local storage.
            paths: Specific paths to sync. If None, sync all files.

        Returns:
            Sync result with counts.
        """
        result = {"uploaded": 0, "skipped": 0, "failed": 0, "errors": []}

        if paths is None:
            # Sync all files
            all_files: list[str] = []
            for root, _, files in os.walk(local_root):
                for f in files:
                    if f.startswith("."):
                        continue
                    full_path = Path(root) / f
                    rel_path = str(full_path.relative_to(local_root))
                    all_files.append(rel_path)
            paths = all_files

        for rel_path in paths:
            try:
                local_path = local_root / rel_path
                if not local_path.exists():
                    result["skipped"] += 1
                    continue

                # Read from local
                async with aiofiles.open(local_path, "rb") as f:
                    data = await f.read()

                # Write to server
                await self.write_file(rel_path, data)
                result["uploaded"] += 1
            except Exception as e:
                result["failed"] += 1
                result["errors"].append(f"{rel_path}: {e}")

        logger.info(
            f"Server sync completed: {result['uploaded']} uploaded, "
            f"{result['skipped']} skipped, {result['failed']} failed"
        )
        return result

    async def close(self) -> None:
        """Clean up resources."""
        self._metadata_cache.clear()
