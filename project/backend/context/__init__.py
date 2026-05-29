"""Context OS v2 module for backend.

Provides a complete context management system for LLM agents:

- ContextBuilder: Core context assembly with token budget enforcement
- ContextProfile: Three-tier resource allocation (cheap/balanced/max) + auto-scaling
- ModelCapability: Model capability registry with YAML support
- TokenBudget: Progressive compression threshold management + component budgets
- MemorySelector: Simplified user memory recall
- CompressionEngine: Five-phase progressive compression
- ToolResultManager: Five-stage tool result lifecycle
- WorkspaceContext: Working set tracking and resource:// URI scheme
- ContextPreview: Context assembly preview with token breakdown

Usage::

    from context import ContextBuilder, get_profile, resolve_model_capability

    builder = ContextBuilder()
    profile = get_profile("balanced")
    model = resolve_model_capability("deepseek-chat")
    context = await builder.build(
        conversation_id="...",
        user_query="Hello",
        model_id="deepseek-chat",
        profile_name="balanced",
    )
"""

from __future__ import annotations

from .compression_engine import (
    CompressionEngine,
    CompressionResult,
    CompressionStrategy,
)
from .context_builder import (
    BuiltContext,
    ContextBuilder,
    ContextState,
    ContextUsage,
)
from .context_preview import (
    ContextPreview,
    ContextPreviewResponse,
    PreviewBlock,
)
from .context_profile import (
    CONTEXT_PROFILES,
    ContextProfile,
    get_profile,
    get_profile_for_model,
    list_profiles,
    scale_profile_for_model,
    update_custom_profile,
)
from .memory_selector import (
    MemoryRecallResult,
    MemorySelector,
    UserMemory,
)
from .model_capability import (
    ModelCapability,
    ModelCapabilityRegistry,
    get_registry,
    list_registered_models,
    register_model_capability,
    resolve_model_capability,
)
from .token_budget import (
    BudgetStatus,
    TokenBudget,
    calculate_token_budget,
    check_budget,
    estimate_tokens,
    get_compression_level,
)
from .tool_result_lifecycle import (
    LifecycleStage,
    ToolResult,
    ToolResultManager,
    ToolResultReference,
    get_tool_result_manager,
)
from .workspace_context import (
    FileChunk,
    WorkingSetEntry,
    WorkspaceContext,
    get_workspace_context,
    make_resource_uri,
    parse_resource_uri,
)

__all__ = [
    # Context Builder
    "ContextBuilder",
    "BuiltContext",
    "ContextState",
    "ContextUsage",
    # Context Preview
    "ContextPreview",
    "ContextPreviewResponse",
    "PreviewBlock",
    # Context Profile
    "ContextProfile",
    "CONTEXT_PROFILES",
    "get_profile",
    "get_profile_for_model",
    "list_profiles",
    "scale_profile_for_model",
    "update_custom_profile",
    # Model Capability
    "ModelCapability",
    "ModelCapabilityRegistry",
    "get_registry",
    "resolve_model_capability",
    "list_registered_models",
    "register_model_capability",
    # Token Budget
    "TokenBudget",
    "BudgetStatus",
    "calculate_token_budget",
    "check_budget",
    "get_compression_level",
    "estimate_tokens",
    # Memory Selector
    "MemorySelector",
    "UserMemory",
    "MemoryRecallResult",
    # Compression Engine
    "CompressionEngine",
    "CompressionResult",
    "CompressionStrategy",
    # Tool Result Lifecycle
    "ToolResultManager",
    "ToolResult",
    "ToolResultReference",
    "LifecycleStage",
    "get_tool_result_manager",
    # Workspace Context
    "WorkspaceContext",
    "WorkingSetEntry",
    "FileChunk",
    "get_workspace_context",
    "make_resource_uri",
    "parse_resource_uri",
]
