"""Upload handling service for the Agent system."""

from __future__ import annotations

import hashlib
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core.config import settings
from core.errors import ValidationError
from core.logging import get_logger
from core.security import sanitize_filename
from services.file_parser import get_file_parser

logger = get_logger(__name__)

MAX_FILES_PER_BATCH = 10
MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_BATCH_SIZE = 50 * 1024 * 1024
MAX_RAW_TEXT = 100_000
MAX_CONTEXT_PER_FILE = 8_000
MAX_CONTEXT_PER_BATCH = 20_000

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf", ".doc", ".docx", ".ppt", ".pptx"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | IMAGE_EXTENSIONS


class UploadResult(BaseModel):
    """Result of saving and parsing an uploaded file."""

    file_id: str
    original_name: str
    safe_name: str
    mime_type: str
    ext: str
    size: int
    workspace_path: str
    absolute_path: str
    created_at: str
    status: str
    text_extracted: bool = False
    text_length: int = 0
    text_preview: str = ""
    context_policy: str = "none"
    resource_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    @property
    def file_name(self) -> str:
        return self.original_name

    @property
    def file_path(self) -> str:
        return self.absolute_path

    @property
    def file_size(self) -> int:
        return self.size

    def to_dict(self) -> dict[str, Any]:
        """Return both modern camelCase fields and legacy snake_case aliases."""
        data = {
            "id": self.file_id,
            "originalName": self.original_name,
            "safeName": self.safe_name,
            "mimeType": self.mime_type,
            "ext": self.ext,
            "size": self.size,
            "workspacePath": self.workspace_path,
            "createdAt": self.created_at,
            "status": self.status,
            "textExtracted": self.text_extracted,
            "textLength": self.text_length,
            "textPreview": self.text_preview,
            "contextPolicy": self.context_policy,
            "resourceUri": self.resource_uri,
            "metadata": self.metadata,
            "error": self.error,
            # Legacy compatibility:
            "file_id": self.file_id,
            "file_name": self.original_name,
            "file_path": self.absolute_path,
            "file_size": self.size,
            "mime_type": self.mime_type,
            "resource_uri": self.resource_uri,
        }
        return data


def _guess_mime_type(file_name: str, provided: str | None = None) -> str:
    if provided and provided != "application/octet-stream":
        return provided
    guessed, _ = mimetypes.guess_type(file_name)
    return guessed or "application/octet-stream"


def _context_policy(ext: str, text_length: int, is_image: bool) -> str:
    if is_image:
        return "weak"
    if text_length <= 0:
        return "none"
    if text_length <= MAX_CONTEXT_PER_FILE:
        return "normal"
    return "compressed"


class UploadService:
    """Validate, save, parse, and describe uploaded files."""

    def __init__(self, upload_root: str | None = None) -> None:
        self.upload_root = Path(upload_root or settings.workspace_root)

    def _get_upload_dir(self, conversation_id: str) -> Path:
        date_part = datetime.now(timezone.utc).date().isoformat()
        upload_dir = self.upload_root / conversation_id / "uploads" / date_part
        upload_dir.mkdir(parents=True, exist_ok=True)
        return upload_dir

    @staticmethod
    def _generate_file_id(file_name: str) -> str:
        hash_input = f"{file_name}_{uuid.uuid4().hex}"
        return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def validate_batch_specs(files: list[tuple[str, int]]) -> None:
        if len(files) > MAX_FILES_PER_BATCH:
            raise ValidationError(
                detail=f"Too many files. Maximum is {MAX_FILES_PER_BATCH}.",
                error_code="TOO_MANY_FILES",
            )
        total_size = sum(size for _, size in files)
        if total_size > MAX_BATCH_SIZE:
            raise ValidationError(
                detail=f"Total upload size exceeds {MAX_BATCH_SIZE} bytes.",
                error_code="BATCH_TOO_LARGE",
            )

    async def upload_file(
        self,
        conversation_id: str,
        file_name: str,
        file_data: bytes,
        mime_type: str | None = None,
    ) -> UploadResult:
        safe_original = sanitize_filename(Path(file_name).name or "unnamed")
        ext = Path(safe_original).suffix.lower()
        detected_mime = _guess_mime_type(safe_original, mime_type)
        now = datetime.now(timezone.utc).isoformat()

        if ext not in ALLOWED_EXTENSIONS:
            raise ValidationError(
                detail=f"File extension '{ext or '(none)'}' is not allowed.",
                error_code="INVALID_FILE_TYPE",
            )
        if not file_data:
            raise ValidationError(detail="File is empty.", error_code="EMPTY_FILE")
        if len(file_data) > MAX_FILE_SIZE:
            raise ValidationError(
                detail=f"File size {len(file_data)} exceeds {MAX_FILE_SIZE} bytes.",
                error_code="FILE_TOO_LARGE",
            )

        file_id = self._generate_file_id(safe_original)
        upload_dir = self._get_upload_dir(conversation_id)
        safe_name = f"{file_id}_{safe_original}"
        file_path = upload_dir / safe_name
        file_path.write_bytes(file_data)

        workspace_path = str(file_path.relative_to(self.upload_root / conversation_id)).replace("\\", "/")
        resource_uri = f"resource://workspace/{workspace_path}"
        is_image = ext in IMAGE_EXTENSIONS
        status = "uploaded"
        text = ""
        text_preview = ""
        text_length = 0
        text_extracted = False
        error: str | None = None
        metadata: dict[str, Any] = {"conversation_id": conversation_id}

        if not is_image:
            parser = get_file_parser()
            parse_result = await parser.parse(str(file_path), detected_mime)
            metadata.update(parse_result.metadata)
            if parse_result.success and parse_result.text:
                text = parse_result.text[:MAX_RAW_TEXT]
                text_length = len(text)
                text_preview = text[:500]
                text_extracted = True
                status = "parsed"
            else:
                status = "failed"
                error = parse_result.error or "No text extracted."

        logger.info(
            "Uploaded file processed",
            extra={
                "conversation_id": conversation_id,
                "file_id": file_id,
                "workspace_path": workspace_path,
                "status": status,
            },
        )

        return UploadResult(
            file_id=file_id,
            original_name=safe_original,
            safe_name=safe_name,
            mime_type=detected_mime,
            ext=ext.lstrip("."),
            size=len(file_data),
            workspace_path=workspace_path,
            absolute_path=str(file_path),
            created_at=now,
            status=status,
            text_extracted=text_extracted,
            text_length=text_length,
            text_preview=text_preview,
            context_policy="weak",
            resource_uri=resource_uri,
            metadata=metadata,
            error=error,
        )

    async def get_upload_status(self, conversation_id: str, file_id: str) -> dict[str, Any]:
        upload_root = self.upload_root / conversation_id / "uploads"
        if not upload_root.exists():
            return {"file_id": file_id, "exists": False, "status": "not_found"}
        for file_path in upload_root.rglob(f"{file_id}_*"):
            if file_path.is_file():
                return {
                    "file_id": file_id,
                    "exists": True,
                    "file_name": file_path.name.split("_", 1)[1] if "_" in file_path.name else file_path.name,
                    "file_size": file_path.stat().st_size,
                    "status": "uploaded",
                }
        return {"file_id": file_id, "exists": False, "status": "not_found"}


_upload_service: UploadService | None = None


def get_upload_service() -> UploadService:
    """Get the global upload service instance."""
    global _upload_service
    if _upload_service is None:
        _upload_service = UploadService()
    return _upload_service
