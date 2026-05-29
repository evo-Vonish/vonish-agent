"""Storage Provider abstract base class for Workspace system.

Defines the interface for storage backends (local, server, cloud).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, AsyncGenerator


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class FileInfo(BaseModel):
    """Information about a file in storage."""

    name: str
    path: str
    size: int
    mime_type: str
    is_directory: bool
    modified_at: datetime | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StorageStats(BaseModel):
    """Statistics about storage usage."""

    total_files: int
    total_size: int
    max_size: int
    available_size: int


# ---------------------------------------------------------------------------
# Abstract Storage Provider
# ---------------------------------------------------------------------------


class StorageProvider(ABC):
    """Abstract base class for workspace storage providers.

    All storage backends (local filesystem, server, cloud) must
    implement this interface.
    """

    @abstractmethod
    async def read_file(self, path: str) -> bytes:
        """Read a file from storage.

        Args:
            path: Relative path within workspace.

        Returns:
            File contents as bytes.

        Raises:
            FileNotFoundError: If file does not exist.
            PermissionError: If read access is denied.
        """
        ...

    @abstractmethod
    async def write_file(self, path: str, data: bytes) -> None:
        """Write a file to storage.

        Args:
            path: Relative path within workspace.
            data: File contents as bytes.

        Raises:
            PermissionError: If write access is denied.
            ValueError: If file exceeds size limits.
        """
        ...

    @abstractmethod
    async def delete_file(self, path: str) -> None:
        """Delete a file from storage.

        Args:
            path: Relative path within workspace.

        Raises:
            FileNotFoundError: If file does not exist.
        """
        ...

    @abstractmethod
    async def list_files(
        self, path: str = "", recursive: bool = False
    ) -> list[FileInfo]:
        """List files in a directory.

        Args:
            path: Relative directory path (empty for root).
            recursive: Whether to list recursively.

        Returns:
            List of FileInfo objects.
        """
        ...

    @abstractmethod
    async def file_exists(self, path: str) -> bool:
        """Check if a file exists.

        Args:
            path: Relative path within workspace.

        Returns:
            True if file exists.
        """
        ...

    @abstractmethod
    async def get_file_info(self, path: str) -> FileInfo | None:
        """Get information about a file.

        Args:
            path: Relative path within workspace.

        Returns:
            FileInfo or None if file does not exist.
        """
        ...

    @abstractmethod
    async def create_directory(self, path: str) -> None:
        """Create a directory.

        Args:
            path: Relative directory path.
        """
        ...

    @abstractmethod
    async def delete_directory(self, path: str, recursive: bool = False) -> None:
        """Delete a directory.

        Args:
            path: Relative directory path.
            recursive: Whether to delete contents recursively.
        """
        ...

    @abstractmethod
    async def move_file(self, source: str, destination: str) -> None:
        """Move/rename a file.

        Args:
            source: Source relative path.
            destination: Destination relative path.
        """
        ...

    @abstractmethod
    async def copy_file(self, source: str, destination: str) -> None:
        """Copy a file.

        Args:
            source: Source relative path.
            destination: Destination relative path.
        """
        ...

    @abstractmethod
    async def get_stats(self) -> StorageStats:
        """Get storage statistics.

        Returns:
            StorageStats with usage information.
        """
        ...

    @abstractmethod
    async def stream_file(self, path: str) -> AsyncGenerator[bytes, None]:
        """Stream a file's contents.

        Args:
            path: Relative path within workspace.

        Yields:
            File content chunks.
        """
        ...

    async def close(self) -> None:
        """Close any open connections. Override if needed."""
        pass
