"""DeckDesignSpec builder.

Normalises the loose, forgiving JSON the agent emits (``slides`` as a list of
dicts with a ``layout`` and content fields) into a strict ``DeckDesignSpec``.
The agent never has to know the exact pydantic shape — it picks a layout and
provides content; this module coerces it.
"""
from __future__ import annotations

from typing import Any

from .registry import get_layout_registry, get_theme_registry
from .schema import (
    Canvas,
    DeckDesignSpec,
    SlideContent,
    SlideSpec,
)


def _as_list(v: Any) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _norm_steps(items: Any) -> list[dict]:
    out = []
    for it in _as_list(items):
        if isinstance(it, str):
            out.append({"title": it})
        elif isinstance(it, dict):
            out.append({"title": it.get("title", ""), "body": it.get("body", ""),
                        "label": it.get("label", "")})
    return out


def _norm_cards(cards: Any) -> list[dict]:
    out = []
    for c in _as_list(cards):
        if isinstance(c, str):
            out.append({"title": c, "body": ""})
        elif isinstance(c, dict):
            out.append({"title": c.get("title", ""), "body": c.get("body", ""),
                        "icon": c.get("icon", "")})
    return out


def _norm_column(col: Any) -> dict | None:
    if col is None:
        return None
    if isinstance(col, str):
        return {"title": "", "body": col, "bullets": []}
    if isinstance(col, dict):
        return {"title": col.get("title", ""), "body": col.get("body", ""),
                "bullets": [str(s) for s in _as_list(col.get("bullets"))]}
    return None


def _norm_content(d: dict) -> SlideContent:
    data: dict[str, Any] = {}
    for key in ("title", "subtitle", "meta", "chapter_number", "body", "footer"):
        if d.get(key) is not None:
            data[key] = str(d[key])
    if d.get("bullets") is not None:
        data["bullets"] = [str(s) for s in _as_list(d["bullets"])]
    if d.get("emphasis") is not None:
        data["emphasis"] = [str(s) for s in _as_list(d["emphasis"])]
    if d.get("cards") is not None:
        data["cards"] = _norm_cards(d["cards"])
    if d.get("items") is not None:
        data["items"] = _norm_steps(d["items"])
    if d.get("steps") is not None:
        data["items"] = _norm_steps(d["steps"])
    if d.get("left") is not None:
        data["left"] = _norm_column(d["left"])
    if d.get("right") is not None:
        data["right"] = _norm_column(d["right"])
    for passthrough in ("chart", "code", "quote", "diagram"):
        if d.get(passthrough) is not None:
            data[passthrough] = d[passthrough]
    return SlideContent.model_validate(data)


def _slide_from_dict(d: dict) -> SlideSpec:
    layout = d.get("layout_id") or d.get("layout") or "summary-bullets"
    if not get_layout_registry().has(layout):
        layout = "summary-bullets"
    content = _norm_content(d)
    return SlideSpec(layout_id=layout, content=content, notes=str(d.get("notes", "")))


def build_deck_spec(
    title: str,
    theme_id: str,
    slides: list[dict],
    *,
    deck_id: str = "",
    canvas: dict | None = None,
) -> DeckDesignSpec:
    if not get_theme_registry().has(theme_id):
        theme_id = "tech-dark"
    canvas_model = Canvas(**canvas) if canvas else Canvas()
    slide_specs = [_slide_from_dict(s if isinstance(s, dict) else {}) for s in (slides or [])]
    return DeckDesignSpec(
        deck_id=deck_id, title=title or "", theme_id=theme_id,
        canvas=canvas_model, slides=slide_specs)
