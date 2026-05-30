"""Small LLM-backed summarizers for UI labels.

These helpers intentionally return short display strings. They do not affect the
agent context and fall back to deterministic truncation if the provider call
fails.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agent.model_adapter import MessageBlock, ModelAdapterFactory
from core.config import MODEL_CONFIGS
from core.logging import get_logger
from services.api_config_service import get_default_api_config

logger = get_logger(__name__)


def _first_phrase(text: str, max_chars: int) -> str:
    compact = " ".join(str(text or "").split()).strip()
    if not compact:
        return ""
    for marker in ("。", "！", "？", ".", "!", "?"):
        if marker in compact:
            compact = compact.split(marker, 1)[0].strip()
            break
    compact = compact.strip("`'\"“”‘’[]()（）:：#*- ")
    return compact[:max_chars].strip() or ""


def _clean_label(text: str, fallback: str, max_chars: int) -> str:
    first_line = str(text or "").strip().splitlines()[0] if str(text or "").strip() else ""
    label = first_line.strip("`'\"“”‘’[]()（）#*- ")
    for prefix in ("标题:", "标题：", "摘要:", "摘要：", "短语:", "短语："):
        if label.startswith(prefix):
            label = label[len(prefix):].strip()
    label = " ".join(label.split())
    if not label:
        label = fallback
    return label[:max_chars].strip() or fallback


async def _complete_short_text(
    *,
    db: AsyncSession,
    user_id: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_chars: int,
) -> str:
    provider = MODEL_CONFIGS.get(model).provider if model in MODEL_CONFIGS else ""
    api_config = (
        await get_default_api_config(db, user_id, provider)
        if provider in ("deepseek", "kimi")
        else None
    )
    adapter = ModelAdapterFactory.create(
        model,
        api_key=api_config.api_key if api_config else None,
        api_base=api_config.api_base if api_config else None,
    )

    parts: list[str] = []
    try:
        async for chunk in adapter.stream_chat(
            messages=[MessageBlock(role="user", content=user_prompt)],
            system_prompt=system_prompt,
            tools=None,
            enable_thinking=True,
            json_mode=False,
        ):
            if chunk.get("type") == "text_delta" and chunk.get("content"):
                parts.append(str(chunk["content"]))
            if chunk.get("type") == "done":
                content = chunk.get("content")
                if isinstance(content, dict) and content.get("error"):
                    raise RuntimeError(str(content["error"]))
        return _clean_label("".join(parts), "", max_chars=max_chars)
    finally:
        await adapter.close()


async def summarize_thinking_phrase(
    *,
    db: AsyncSession,
    user_id: str,
    model: str,
    thinking: str,
) -> str:
    fallback = _first_phrase(thinking, 18) or "思考过程"
    excerpt = str(thinking or "")[:4000]
    if not excerpt.strip():
        return fallback

    try:
        label = await _complete_short_text(
            db=db,
            user_id=user_id,
            model=model,
            max_chars=32,
            system_prompt=(
                "你是界面文案压缩器。只输出一个极短短语，不要解释，"
                "不要复述推理细节，不要使用标点。"
            ),
            user_prompt=(
                "把下面的思考过程概括成 4 到 12 个中文字的短语，"
                "只描述当前阶段动作。\n\n"
                f"{excerpt}"
            ),
        )
        return label or fallback
    except Exception as exc:
        logger.warning("Thinking summary failed", extra={"error": str(exc)[:500]})
        return fallback


async def summarize_conversation_title(
    *,
    db: AsyncSession,
    user_id: str,
    model: str,
    messages: list[dict[str, Any]],
) -> str:
    clipped: list[str] = []
    for item in messages[:4]:
        role = str(item.get("role", "message"))
        content = " ".join(str(item.get("content", "")).split())[:320]
        if content:
            clipped.append(f"{role}: {content}")

    excerpt = "\n".join(clipped)
    fallback = _first_phrase(messages[0].get("content", "") if messages else "", 24) or "新对话"
    if not excerpt:
        return fallback

    try:
        label = await _complete_short_text(
            db=db,
            user_id=user_id,
            model=model,
            max_chars=24,
            system_prompt=(
                "你是对话标题生成器。只输出标题本身，不要解释，不要引号，"
                "标题应短、具体，最多 12 个中文字或 6 个英文词。"
            ),
            user_prompt=f"根据以下对话片段生成标题：\n\n{excerpt}",
        )
        return label or fallback
    except Exception as exc:
        logger.warning("Conversation title summary failed", extra={"error": str(exc)[:500]})
        return fallback
