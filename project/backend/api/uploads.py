"""File Upload API routes.

Provides:
- POST /api/uploads/{conversation_id} - Batch upload files
- GET /api/uploads/{conversation_id}/{file_id}/status - Upload status
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import User, get_current_user
from core.logging import get_logger
from core.security import validate_file_size, validate_mime_type
from db.session import get_db
from services.upload_service import get_upload_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class UploadStatusResponse(BaseModel):
    """Upload status response."""

    file_id: str
    status: str
    file_name: str = ""
    file_size: int = 0
    mime_type: str = ""
    error: str | None = None


class UploadBatchResponse(BaseModel):
    """Batch upload response."""

    uploaded: list[dict[str, Any]]
    failed: list[dict[str, Any]]
    total: int
    successful: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/uploads/{conversation_id}", response_model=UploadBatchResponse)
async def upload_files(
    conversation_id: str,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Batch upload files to a conversation.

    Args:
        conversation_id: Target conversation ID.
        files: List of files to upload.
    """
    service = get_upload_service()

    uploaded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for upload_file in files:
        try:
            # Read file data
            file_data = await upload_file.read()

            # Validate
            if not validate_file_size(len(file_data)):
                failed.append(
                    {
                        "file_name": upload_file.filename or "unknown",
                        "error": f"File size {len(file_data)} exceeds 50MB limit",
                    }
                )
                continue

            mime_type = upload_file.content_type or "application/octet-stream"
            if not validate_mime_type(mime_type):
                failed.append(
                    {
                        "file_name": upload_file.filename or "unknown",
                        "error": f"MIME type '{mime_type}' not allowed",
                    }
                )
                continue

            # Upload
            result = await service.upload_file(
                conversation_id=conversation_id,
                file_name=upload_file.filename or "unnamed",
                file_data=file_data,
                mime_type=mime_type,
            )

            uploaded.append(result.to_dict())

            logger.info(
                f"Uploaded file: {result.file_name}",
                extra={
                    "conversation_id": conversation_id,
                    "file_id": result.file_id,
                    "size": result.file_size,
                },
            )

        except Exception as e:
            failed.append(
                {
                    "file_name": upload_file.filename or "unknown",
                    "error": str(e),
                }
            )

    return UploadBatchResponse(
        uploaded=uploaded,
        failed=failed,
        total=len(files),
        successful=len(uploaded),
    )


@router.get("/uploads/{conversation_id}/{file_id}/status")
async def get_upload_status(
    conversation_id: str,
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get the status of an uploaded file.

    Args:
        conversation_id: Conversation ID.
        file_id: File ID.
    """
    service = get_upload_service()
    status = await service.get_upload_status(conversation_id, file_id)

    return UploadStatusResponse(
        file_id=file_id,
        status=status.get("status", "unknown"),
        file_name=status.get("file_name", ""),
        file_size=status.get("file_size", 0),
    )
