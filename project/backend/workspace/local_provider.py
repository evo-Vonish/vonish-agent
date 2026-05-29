"""Local Storage Provider for Workspace system.

Implements StorageProvider using the local filesystem with aiofiles
for fully asynchronous I/O operations.
"""

from __future__ import annotations

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
# MIME Type Detection
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

# File type whitelist for uploads
ALLOWED_EXTENSIONS: set[str] = set(MIME_TYPES.keys())

# Maximum file size: 50MB
MAX_FILE_SIZE = 50 * 1024 * 1024


def guess_mime_type(filename: str) -> str:
    """Guess MIME type from filename extension."""
    ext = Path(filename).suffix.lower()
    return MIME_TYPES.get(ext, "application/octet-stream")


def is_allowed_file_type(filename: str) -> bool:
    """Check if file type is in the whitelist."""
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Local Storage Provider
# ---------------------------------------------------------------------------


class LocalStorageProvider(StorageProvider):
    """Storage provider using local filesystem with async I/O.

    All paths are validated through PathSandbox before access.
    Uses aiofiles for non-blocking file operations.
    """

    def __init__(
        self,
        workspace_root: str | Path,
        max_size: int = 500 * 1024 * 1024,  # 500MB default per workspace
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self._sandbox = PathSandbox(self.workspace_root)
        self._max_size = max_size

    def _validate(self, path: str) -> Path:
        """Validate path through sandbox.

        Args:
            path: Relative path within workspace.

        Returns:
            Resolved safe path.

        Raises:
            SecurityError: If path is invalid.
        """
        return self._sandbox.validate_path(path)

    def _validate_create(self, path: str) -> Path:
        """Validate path for creation through sandbox.

        Args:
            path: Relative path within workspace.

        Returns:
            Resolved safe path.

        Raises:
            SecurityError: If path is invalid.
        """
        return self._sandbox.validate_create_path(path)

    async def read_file(self, path: str) -> bytes:
        """Read a file from local storage asynchronously.

        Args:
            path: Relative path within workspace.

        Returns:
            File contents as bytes.

        Raises:
            FileNotFoundError: If file does not exist.
            SecurityError: If path is invalid.
        """
        safe_path = self._validate(path)

        if not safe_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if not safe_path.is_file():
            raise ValueError(f"Path is not a file: {path}")

        async with aiofiles.open(safe_path, "rb") as f:
            return await f.read()

    async def write_file(self, path: str, data: bytes) -> None:
        """Write a file to local storage asynchronously.

        Args:
            path: Relative path within workspace.
            data: File contents as bytes.

        Raises:
            SecurityError: If path is invalid.
            ValueError: If file exceeds size limit or has disallowed type.
        """
        safe_path = self._validate_create(path)

        # Check file size limit
        if len(data) > MAX_FILE_SIZE:
            raise ValueError(
                f"File size {len(data)} exceeds maximum allowed size of {MAX_FILE_SIZE} bytes"
            )

        # Check file type whitelist
        if not is_allowed_file_type(safe_path.name):
            raise ValueError(
                f"File type '{safe_path.suffix}' is not allowed. "
                f"Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )

        # Create parent directories asynchronously
        parent = safe_path.parent
        if parent != self.workspace_root:
            parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(safe_path, "wb") as f:
            await f.write(data)

        logger.debug(f"Written file: {safe_path} ({len(data)} bytes)")

    async def delete_file(self, path: str) -> None:
        """Delete a file from local storage.

        Args:
            path: Relative path within workspace.

        Raises:
            FileNotFoundError: If file does not exist.
            SecurityError: If path is invalid.
        """
        safe_path = self._validate(path)

        if not safe_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if not safe_path.is_file():
            raise ValueError(f"Path is not a file: {path}")

        await aiofiles.os.remove(safe_path)
        logger.debug(f"Deleted file: {safe_path}")

    async def list_files(
        self, path: str = "", recursive: bool = False
    ) -> list[FileInfo]:
        """List files in local storage.

        Args:
            path: Relative directory path (empty for root).
            recursive: Whether to list recursively.

        Returns:
            List of FileInfo objects.
        """
        if path:
            safe_path = self._validate(path)
        else:
            safe_path = self.workspace_root

        if not safe_path.exists():
            return []

        if not safe_path.is_dir():
            # Single file
            stat = safe_path.stat()
            rel_path = self._sandbox.get_relative_path(safe_path)
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

                # Add directories
                for d in dirs:
                    dir_path = root_path / d
                    # Skip hidden directories (except .workspace)
                    if d.startswith(".") and d != ".workspace":
                        continue
                    stat = dir_path.stat()
                    rel_path = self._sandbox.get_relative_path(dir_path)
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

                # Add files
                for f in files:
                    # Skip hidden files
                    if f.startswith("."):
                        continue
                    file_path = root_path / f
                    stat = file_path.stat()
                    rel_path = self._sandbox.get_relative_path(file_path)
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
                # Skip hidden entries (except .workspace)
                if entry.name.startswith(".") and entry.name != ".workspace":
                    continue
                stat = entry.stat()
                rel_path = self._sandbox.get_relative_path(Path(entry.path))
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
                        created_at=datetime.fromtimestamp(
                            stat.st_ctime, tz=timezone.utc
                        )
                        if entry.is_file()
                        else None,
                    )
                )

        return result

    async def file_exists(self, path: str) -> bool:
        """Check if file exists in local storage.

        Args:
            path: Relative path within workspace.

        Returns:
            True if file exists.
        """
        try:
            safe_path = self._validate(path)
            return safe_path.exists()
        except (SecurityError, OSError):
            return False

    async def get_file_info(self, path: str) -> FileInfo | None:
        """Get file information from local storage.

        Args:
            path: Relative path within workspace.

        Returns:
            FileInfo or None if file does not exist.
        """
        try:
            safe_path = self._validate(path)

            if not safe_path.exists():
                return None

            stat = safe_path.stat()
            rel_path = self._sandbox.get_relative_path(safe_path)

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
        """Create a directory in local storage.

        Args:
            path: Relative directory path.

        Raises:
            SecurityError: If path is invalid.
        """
        safe_path = self._validate_create(path)
        safe_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Created directory: {safe_path}")

    async def delete_directory(self, path: str, recursive: bool = False) -> None:
        """Delete a directory from local storage.

        Args:
            path: Relative directory path.
            recursive: Whether to delete contents recursively.

        Raises:
            FileNotFoundError: If directory does not exist.
            SecurityError: If path is invalid.
            OSError: If directory is not empty and recursive is False.
        """
        safe_path = self._validate(path)

        if not safe_path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")

        if not safe_path.is_dir():
            raise ValueError(f"Path is not a directory: {path}")

        if recursive:
            await aiofiles.os.wrap(shutil.rmtree)(safe_path)
        else:
            await aiofiles.os.rmdir(safe_path)

        logger.debug(f"Deleted directory: {safe_path}")

    async def move_file(self, source: str, destination: str) -> None:
        """Move/rename a file in local storage.

        Args:
            source: Source relative path.
            destination: Destination relative path.

        Raises:
            FileNotFoundError: If source does not exist.
            SecurityError: If either path is invalid.
        """
        safe_source = self._validate(source)
        safe_dest = self._validate_create(destination)

        if not safe_source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        safe_dest.parent.mkdir(parents=True, exist_ok=True)
        await aiofiles.os.wrap(shutil.move)(str(safe_source), str(safe_dest))
        logger.debug(f"Moved file: {safe_source} -> {safe_dest}")

    async def copy_file(self, source: str, destination: str) -> None:
        """Copy a file in local storage.

        Args:
            source: Source relative path.
            destination: Destination relative path.

        Raises:
            FileNotFoundError: If source does not exist.
            SecurityError: If either path is invalid.
        """
        safe_source = self._validate(source)
        safe_dest = self._validate_create(destination)

        if not safe_source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        safe_dest.parent.mkdir(parents=True, exist_ok=True)
        await aiofiles.os.wrap(shutil.copy2)(str(safe_source), str(safe_dest))
        logger.debug(f"Copied file: {safe_source} -> {safe_dest}")

    async def get_stats(self) -> StorageStats:
        """Get storage statistics.

        Returns:
            StorageStats with usage information.
        """
        total_size = 0
        total_files = 0

        for root, _, files in os.walk(self.workspace_root):
            for f in files:
                # Skip hidden files
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
        """Stream a file's contents asynchronously.

        Args:
            path: Relative path within workspace.

        Yields:
            File content chunks (64KB each).

        Raises:
            FileNotFoundError: If file does not exist.
            SecurityError: If path is invalid.
        """
        safe_path = self._validate(path)

        if not safe_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        chunk_size = 64 * 1024  # 64KB chunks
        async with aiofiles.open(safe_path, "rb") as f:
            while True:
                chunk = await f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    async def read_file_with_timeout(self, path: str, timeout: float = 30.0) -> bytes:
        """Read a file with a timeout.

        Args:
            path: Relative path within workspace.
            timeout: Maximum time in seconds to wait for read.

        Returns:
            File contents as bytes.

        Raises:
            TimeoutError: If read exceeds timeout.
            FileNotFoundError: If file does not exist.
        """
        import asyncio

        safe_path = self._validate(path)

        if not safe_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        async def _read() -> bytes:
            async with aiofiles.open(safe_path, "rb") as f:
                return await f.read()

        return await asyncio.wait_for(_read(), timeout=timeout)
