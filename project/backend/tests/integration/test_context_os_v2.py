"""Integration tests for Context OS v2."""
import pytest

from context.model_capability import ModelCapability
from context.context_profile import get_profile, scale_profile_for_model
from context.token_budget import calculate_token_budget
from context.tool_result_lifecycle import LifecycleStage, ToolResultReference
from context.workspace_context import make_resource_uri, parse_resource_uri


def test_cheap_profile():
    """Compatibility profiles use the fixed minimal context policy."""
    profile = get_profile("cheap")
    assert profile.max_input_tokens == 256000
    assert profile.recent_turns == 5
    assert profile.tool_result_mode == "hybrid"
    assert profile.enable_cycle_advance is False


def test_balanced_profile():
    """Balanced no longer enables compression or history trimming."""
    profile = get_profile("balanced")
    assert profile.max_input_tokens == 256000
    assert profile.recent_turns == 5
    assert profile.tool_result_mode == "hybrid"
    assert profile.compression_level == "minimal"


def test_max_profile():
    """Max maps to the same fixed policy as all compatibility profiles."""
    profile = get_profile("max")
    assert profile.max_input_tokens == 256000
    assert profile.recent_turns == 5
    assert profile.tool_result_mode == "hybrid"


def test_model_scaling_64k():
    """Test profile scaling for 64K context window model."""
    model = ModelCapability(
        provider="ds",
        model_id="ds-chat",
        context_window=65536,
        max_output_tokens=8192,
    )
    profile = get_profile("cheap")
    scaled = scale_profile_for_model(profile, model)
    assert scaled.max_input_tokens <= 65536


def test_model_scaling_1m():
    """Test profile scaling for 1M context window model."""
    model = ModelCapability(
        provider="ds",
        model_id="ds-v4",
        context_window=1000000,
        max_output_tokens=8192,
    )
    profile = get_profile("max")
    scaled = scale_profile_for_model(profile, model)
    assert scaled.max_input_tokens == 256000  # unchanged for 1M


def test_token_budget_breakdown():
    """Test token budget calculation produces valid breakdown."""
    model = ModelCapability(
        provider="ds",
        model_id="ds-chat",
        context_window=65536,
        max_output_tokens=8192,
    )
    profile = get_profile("cheap")
    scaled = scale_profile_for_model(profile, model)
    budget = calculate_token_budget(scaled, model)
    assert budget.available_input_budget > 0
    assert "system_prompt" in budget.breakdown
    assert "recent_messages" in budget.breakdown


def test_tool_result_lifecycle_stages():
    """Test lifecycle stage enum values."""
    assert LifecycleStage.FULL.value == "full"
    assert LifecycleStage.SUMMARY.value == "summary"
    assert LifecycleStage.REFERENCE.value == "reference"
    assert LifecycleStage.ARCHIVED.value == "archived"
    assert LifecycleStage.EVICTED.value == "evicted"


def test_resource_uri():
    """Test resource URI creation and parsing."""
    uri = make_resource_uri("uploads/report.pdf")
    assert uri == "resource://workspace/uploads/report.pdf"
    path = parse_resource_uri(uri)
    assert path == "uploads/report.pdf"
