"""Unit tests for file operation tools."""
import asyncio
import tempfile
import pytest
from pathlib import Path

from tools.context import ToolContext
from tools.file_tools import ReadFileTool, WriteFileTool, EditFileTool, DeleteFileTool


@pytest.fixture
def ctx():
    """Create a test ToolContext with a temporary workspace."""
    workspace = tempfile.mkdtemp()
    return ToolContext(conversation_id="test", workspace_root=workspace, user_id="user")


@pytest.mark.anyio
async def test_write_file(ctx):
    """Test writing a file."""
    tool = WriteFileTool()
    result = await tool.execute(ctx, path="test.md", content="# Hello")
    assert result.success
    assert result.diff is not None


@pytest.mark.anyio
async def test_read_file(ctx):
    """Test reading a file after writing."""
    # Write first
    await WriteFileTool().execute(ctx, path="test.md", content="# Hello")
    result = await ReadFileTool().execute(ctx, path="test.md")
    assert result.success
    assert "Hello" in result.output


@pytest.mark.anyio
async def test_edit_file_exact(ctx):
    """Test exact match edit."""
    await WriteFileTool().execute(ctx, path="test.md", content="# Hello World")
    result = await EditFileTool().execute(ctx, path="test.md", old_text="Hello World", new_text="Hi Agent")
    assert result.success


@pytest.mark.anyio
async def test_edit_file_multi_match_fails(ctx):
    """Test that multi-match edit fails."""
    await WriteFileTool().execute(ctx, path="multi.txt", content="hello a\nhello b")
    result = await EditFileTool().execute(ctx, path="multi.txt", old_text="hello", new_text="hi")
    assert not result.success


@pytest.mark.anyio
async def test_path_escape_blocked(ctx):
    """Test path traversal is blocked."""
    result = await ReadFileTool().execute(ctx, path="../../etc/passwd")
    assert not result.success


@pytest.mark.anyio
async def test_delete_workspace_blocked(ctx):
    """Test deleting workspace files is blocked."""
    result = await DeleteFileTool().execute(ctx, path=".workspace/config.json")
    assert not result.success
