"""Upload handling service for the Agent system.

Manages file uploads, validation, storage, and processing triggers.
"""

from __future__ import annotations

import hashlib
import shutil
import uuid
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Any

from core.config import settings
from core.errors import ValidationError
from core.logging import get_logger
from core.security import ALLOWED_MIME_TYPES, MAX_UPLOAD_SIZE, validate_mime_type

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class UploadResult(BaseModel):
    """Result of a file upload."""

    file_id: str
    file_name: str
    file_path: str
    file_size: int
    mime_type: str
    status: str  # uploaded / parsing / parsed / indexed / failed
    resource_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "status": self.status,
            "resource_uri": self.resource_uri,
            "metadata": self.metadata,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Upload Service
# ---------------------------------------------------------------------------


class UploadService:
    """Service for handling file uploads.

    Validates, stores, and tracks uploaded files.
    Coordinates with parsing and indexing services.
    """

    def __init__(self, upload_root: str | None = None) -> None:
        self.upload_root = Path(upload_root or settings.workspace_root)

    def _get_upload_dir(self, conversation_id: str) -> Path:
        """Get the upload directory for a conversation."""
        upload_dir = self.upload_root / conversation_id / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        return upload_dir

    def _generate_file_id(self, file_name: str) -> str:
        """Generate a unique file ID."""
        hash_input = f"{file_name}_{uuid.uuid4().hex}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    async def upload_file(
        self,
        conversation_id: str,
        file_name: str,
        file_data: bytes,
        mime_type: str | None = None,
    ) -> UploadResult:
        """Upload and store a file.

        Args:
            conversation_id: Target conversation ID.
            file_name: Original file name.
            file_data: File content as bytes.
            mime_type: MIME type (auto-detected if not provided).

        Returns:
            UploadResult with file metadata.

        Raises:
            ValidationError: If file validation fails.
        """
        # Validate file size
        if len(file_data) > MAX_UPLOAD_SIZE:
            raise ValidationError(
                detail=f"File size {len(file_data)} exceeds maximum {MAX_UPLOAD_SIZE}",
                error_code="FILE_TOO_LARGE",
            )

        # Validate MIME type
        detected_mime = mime_type or "application/octet-stream"
        if not validate_mime_type(detected_mime):
            raise ValidationError(
                detail=f"File type '{detected_mime}' is not allowed",
                error_code="INVALID_FILE_TYPE",
            )

        # Generate file ID and path
        file_id = self._generate_file_id(file_name)
        upload_dir = self._get_upload_dir(conversation_id)
        safe_name = Path(file_name).name
        file_path = upload_dir / f"{file_id}_{safe_name}"

        # Write file
        file_path.write_bytes(file_data)

        resource_uri = f"resource://workspace/{conversation_id}/uploads/{safe_name}"

        logger.info(
            f"File uploaded: {safe_name} ({len(file_data)} bytes)",
            extra={
                "conversation_id": conversation_id,
                "file_id": file_id,
                "mime_type": detected_mime,
            },
        )

        return UploadResult(
            file_id=file_id,
            file_name=safe_name,
            file_path=str(file_path),
            file_size=len(file_data),
            mime_type=detected_mime,
            status="uploaded",
            resource_uri=resource_uri,
            metadata={
                "conversation_id": conversation_id,
                "original_name": file_name,
            },
        )

    async def upload_batch(
        self,
        conversation_id: str,
        files: list[tuple[str, bytes]],
    ) -> list[UploadResult]:
        """Upload multiple files.

        Args:
            conversation_id: Target conversation ID.
            files: List of (file_name, file_data) tuples.

        Returns:
            List of UploadResult objects.
        """
        results: list[UploadResult] = []
        for file_name, file_data in files:
            try:
                result = await self.upload_file(conversation_id, file_name, file_data)
                results.append(result)
            except ValidationError as e:
                results.append(
                    UploadResult(
                        file_id="",
                        file_name=file_name,
                        file_path="",
                        file_size=len(file_data),
                        mime_type="unknown",
                        status="failed",
                        error=e.detail,
                    )
                )
        return results

    async def delete_upload(self, conversation_id: str, file_id: str) -> bool:
        """Delete an uploaded file.

        Args:
            conversation_id: Conversation ID.
            file_id: File ID to delete.

        Returns:
            True if file was deleted.
        """
        upload_dir = self._get_upload_dir(conversation_id)

        # Find file by ID prefix
        for file_path in upload_dir.iterdir():
            if file_path.name.startswith(file_id):
                file_path.unlink()
                logger.info(f"Deleted upload: {file_id}")
                return True

        return False

    async def get_upload_status(self, conversation_id: str, file_id: str) -> dict[str, Any]:
        """Get the status of an uploaded file.

        Args:
            conversation_id: Conversation ID.
            file_id: File ID.

        Returns:
            Status dictionary.
        """
        upload_dir = self._get_upload_dir(conversation_id)

        for file_path in upload_dir.iterdir():
            if file_path.name.startswith(file_id):
                return {
                    "file_id": file_id,
                    "exists": True,
                    "file_name": file_path.name.split("_", 1)[1]
                    if "_" in file_path.name
                    else file_path.name,
                    "file_size": file_path.stat().st_size,
                    "status": "uploaded",
                }

        return {"file_id": file_id, "exists": False, "status": "not_found"}

    async def list_uploads(self, conversation_id: str) -> list[dict[str, Any]]:
        """List all uploaded files for a conversation.

        Args:
            conversation_id: Conversation ID.

        Returns:
            List of file metadata dictionaries.
        """
        upload_dir = self._get_upload_dir(conversation_id)
        results: list[dict[str, Any]] = []

        for file_path in upload_dir.iterdir():
            if file_path.is_file():
                name_parts = file_path.name.split("_", 1)
                file_id = name_parts[0] if len(name_parts) > 1 else ""
                file_name = name_parts[1] if len(name_parts) > 1 else file_path.name

                results.append(
                    {
                        "file_id": file_id,
                        "file_name": file_name,
                        "file_size": file_path.stat().st_size,
                        "file_path": str(file_path),
                    }
                )

        return results


# ---------------------------------------------------------------------------
# Global Instance
# ---------------------------------------------------------------------------

_upload_service: UploadService | None = None


def get_upload_service() -> UploadService:
    """Get the global upload service instance."""
    global _upload_service
    if _upload_service is None:
        _upload_service = UploadService()
    return _upload_service
