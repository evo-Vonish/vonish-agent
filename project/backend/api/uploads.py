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
from db.session import get_db
from services.upload_service import MAX_CONTEXT_PER_BATCH, get_upload_service

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
    buffered: list[tuple[UploadFile, bytes]] = []

    for upload_file in files:
        try:
            file_data = await upload_file.read()
            buffered.append((upload_file, file_data))
        except Exception as e:
            failed.append({"file_name": upload_file.filename or "unknown", "error": str(e)})

    try:
        service.validate_batch_specs(
            [(upload_file.filename or "unknown", len(file_data)) for upload_file, file_data in buffered]
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    context_used = 0

    for upload_file, file_data in buffered:
        try:
            mime_type = upload_file.content_type or "application/octet-stream"
            result = await service.upload_file(
                conversation_id=conversation_id,
                file_name=upload_file.filename or "unnamed",
                file_data=file_data,
                mime_type=mime_type,
            )
            result_dict = result.to_dict()
            context_text = str(result_dict.get("contextText") or "")
            if context_text:
                remaining = max(0, MAX_CONTEXT_PER_BATCH - context_used)
                result_dict["contextText"] = context_text[:remaining]
                context_used += len(result_dict["contextText"])

            uploaded.append(result_dict)

            try:
                from context.workspace_context import get_workspace_context

                get_workspace_context().touch_file(
                    conversation_id,
                    result.workspace_path,
                    source="upload",
                )
            except Exception as ctx_error:
                logger.warning(f"Failed to touch uploaded file context: {ctx_error}")

            logger.info(
                f"Uploaded file: {result.original_name}",
                extra={
                    "conversation_id": conversation_id,
                    "file_id": result.file_id,
                    "size": result.size,
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
