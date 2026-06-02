import pytest

from agent.tool_executor import ToolCallRequest, ToolExecutor
from agent.tool_registry import register_default_tools
from api.prompt import get_enabled_tools, set_tool_enabled
from tools.research_runtime_client import HollowSearchCoreClient


@pytest.mark.anyio
async def test_research_fetch_returns_reference_not_full_text(monkeypatch):
    async def fake_ready(self):
        return {"status": "ok", "engines": ["duckduckgo"]}

    async def fake_request(self, method, path, *, json_data=None, timeout=None):
        return {
            "pages": [
                {
                    "url": "https://example.com/a",
                    "title": "Example",
                    "text": "Long page body " * 200,
                    "status": "success",
                    "charCount": 3000,
                }
            ],
            "stats": {"total": 1, "succeeded": 1, "failed": 0},
        }

    monkeypatch.setattr(HollowSearchCoreClient, "ensure_ready", fake_ready)
    monkeypatch.setattr(HollowSearchCoreClient, "_request", fake_request)

    result = await HollowSearchCoreClient().fetch("https://example.com/a")

    assert result["success"] is True
    assert result["content_ref"].startswith("research_")
    assert "text" not in result
    assert len(result["summary"]) < 1000
    assert result["char_count"] == 3000


@pytest.mark.anyio
async def test_research_tool_executor_uses_research_client(monkeypatch):
    register_default_tools()
    set_tool_enabled("research_search", True)

    async def fake_search(self, query, mode="overview", max_results=20, language=None):
        return {
            "success": True,
            "query": query,
            "mode": mode,
            "results": [{"title": "Result", "url": "https://example.com", "snippet": "ok"}],
            "timing_ms": 1,
        }

    monkeypatch.setattr(HollowSearchCoreClient, "search", fake_search)

    result = await ToolExecutor().execute(
        ToolCallRequest(
            tool_name="research_search",
            arguments={"query": "example", "max_results": 1},
            call_id="call_research",
        )
    )

    assert result.success is True
    assert result.result["results"][0]["title"] == "Result"


def test_web_research_tools_enabled_by_default():
    register_default_tools()
    enabled = set(get_enabled_tools())

    assert "research_search" in enabled
    assert "research_fetch" in enabled
    assert "deep_research" in enabled
    assert "web_search" in enabled
    assert "web_fetch" in enabled
