"""SQLAlchemy 2.0 ORM models for the Agent system.

Defines all tables as specified in SPEC.md Section 3.
Uses SQLAlchemy 2.0 declarative style with type annotations.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSON_DATA = JSON().with_variant(JSONB(), "postgresql")
STRING_LIST = JSON().with_variant(ARRAY(String), "postgresql")
FLOAT_LIST = JSON().with_variant(ARRAY(Float), "postgresql")


# ---------------------------------------------------------------------------
# Base Model
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Base class for all ORM models."""

    type_annotation_map = {
        dict[str, Any]: JSON_DATA,
        list[str]: STRING_LIST,
    }


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def new_uuid() -> uuid.UUID:
    """Generate a new UUID."""
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# User Model
# ---------------------------------------------------------------------------

class User(Base):
    """User account model."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=new_uuid
    )
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSON_DATA, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    conversations: Mapped[List["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    memories: Mapped[List["UserMemory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Conversation Model
# ---------------------------------------------------------------------------

class Conversation(Base):
    """Chat conversation model."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=new_uuid
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), default="新对话")
    model: Mapped[str] = mapped_column(String(50), default="deepseek-v4-pro")
    context_profile: Mapped[str] = mapped_column(String(20), default="balanced")
    workspace_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_DATA, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship(back_populates="conversations")
    messages: Mapped[List["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    workspace_files: Mapped[List["WorkspaceFile"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    resources: Mapped[List["Resource"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    tool_calls: Mapped[List["ToolCall"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    conversation_memories: Mapped[List["ConversationMemory"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    snapshots: Mapped[List["WorkspaceSnapshot"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    token_usages: Mapped[List["TokenUsage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    context_builds: Mapped[List["ContextBuild"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Message Model (content blocks)
# ---------------------------------------------------------------------------

class Message(Base):
    """Chat message model with content blocks support."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=new_uuid
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    # Content blocks array: [{"type": "text", "text": "..."}, {"type": "image", ...}]
    content: Mapped[list[dict[str, Any]]] = mapped_column(JSON_DATA, nullable=False)
    thinking_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(
        JSON_DATA, nullable=True
    )  # {input_tokens, output_tokens, cached_tokens}
    model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    tool_calls: Mapped[List["ToolCall"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )
    token_usages: Mapped[List["TokenUsage"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Workspace File Model
# ---------------------------------------------------------------------------

class WorkspaceFile(Base):
    """Workspace file tracking model."""

    __tablename__ = "workspace_files"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=new_uuid
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="uploaded"
    )  # uploaded/parsing/parsed/indexed/failed
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_DATA, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="workspace_files")


# ---------------------------------------------------------------------------
# Resource Model
# ---------------------------------------------------------------------------

class Resource(Base):
    """Resource model for uploaded files and tool outputs."""

    __tablename__ = "resources"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=new_uuid
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # upload | tool_output | crawl_result
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_DATA, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="resources")
    chunks: Mapped[List["ResourceChunk"]] = relationship(
        back_populates="resource", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Resource Chunk Model (with vector embedding)
# ---------------------------------------------------------------------------

class ResourceChunk(Base):
    """Resource chunk model for vector recall."""

    __tablename__ = "resource_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=new_uuid
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Using ARRAY(Float) to simulate pgvector VECTOR(1536)
    # For production: use pgvector extension with proper VECTOR type
    embedding: Mapped[list[float] | None] = mapped_column(
        FLOAT_LIST, nullable=True
    )
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_DATA, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    resource: Mapped["Resource"] = relationship(back_populates="chunks")


# ---------------------------------------------------------------------------
# Tool Call Model
# ---------------------------------------------------------------------------

class ToolCall(Base):
    """Tool call execution record model."""

    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=new_uuid
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id"), nullable=True
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON_DATA, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending/running/completed/failed
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON_DATA, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="tool_calls")
    message: Mapped[Optional["Message"]] = relationship(back_populates="tool_calls")


# ---------------------------------------------------------------------------
# User Memory Model (long-term)
# ---------------------------------------------------------------------------

class UserMemory(Base):
    """User long-term memory model."""

    __tablename__ = "user_memories"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=new_uuid
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    memory_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # preference | fact | profile | task
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Using ARRAY(Float) to simulate pgvector VECTOR(1536)
    embedding: Mapped[list[float] | None] = mapped_column(
        FLOAT_LIST, nullable=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # extracted | user_defined | inferred
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_DATA, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="memories")


# ---------------------------------------------------------------------------
# API Provider Config Model
# ---------------------------------------------------------------------------

class ApiProviderConfig(Base):
    """Persisted API credentials and endpoint configuration."""

    __tablename__ = "api_provider_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=new_uuid
    )
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    api_base: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


# ---------------------------------------------------------------------------
# Conversation Memory Model
# ---------------------------------------------------------------------------

class ConversationMemory(Base):
    """Conversation-level memory model."""

    __tablename__ = "conversation_memories"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=new_uuid
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    memory_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Using ARRAY(Float) to simulate pgvector VECTOR(1536)
    embedding: Mapped[list[float] | None] = mapped_column(
        FLOAT_LIST, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        back_populates="conversation_memories"
    )


# ---------------------------------------------------------------------------
# Workspace Snapshot Model
# ---------------------------------------------------------------------------

class WorkspaceSnapshot(Base):
    """Workspace snapshot model."""

    __tablename__ = "workspace_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=new_uuid
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # before | after
    file_manifest: Mapped[dict[str, Any]] = mapped_column(JSON_DATA, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="snapshots")


# ---------------------------------------------------------------------------
# Token Usage Model
# ---------------------------------------------------------------------------

class TokenUsage(Base):
    """Token usage tracking model."""

    __tablename__ = "token_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=new_uuid
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id"), nullable=True
    )
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    uncached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="token_usages")
    message: Mapped[Optional["Message"]] = relationship(back_populates="token_usages")


# ---------------------------------------------------------------------------
# Context Build Model
# ---------------------------------------------------------------------------

class ContextBuild(Base):
    """Context build record model."""

    __tablename__ = "context_builds"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=new_uuid
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    profile: Mapped[str] = mapped_column(String(20), nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    components: Mapped[dict[str, Any]] = mapped_column(
        JSON_DATA, nullable=False
    )  # component token usage details
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="context_builds")
