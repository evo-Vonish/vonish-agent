"""Theme & Layout registries — the lookup surface for the engine and the API.

Both are tiny singletons so the agent can list available themes/layouts and the
engine can resolve a spec without re-loading the built-ins each call.
"""
from __future__ import annotations

from typing import Any

from .layouts.recipes import BUILTIN_LAYOUTS, DEFAULT_LAYOUT_ID
from .schema import LayoutRecipe, Theme
from .themes import BUILTIN_THEMES, DEFAULT_THEME_ID


class ThemeRegistry:
    def __init__(self) -> None:
        self._themes: dict[str, Theme] = dict(BUILTIN_THEMES)

    def get(self, theme_id: str | None) -> Theme:
        if theme_id and theme_id in self._themes:
            return self._themes[theme_id]
        return self._themes[DEFAULT_THEME_ID]

    def has(self, theme_id: str) -> bool:
        return theme_id in self._themes

    def register(self, theme: Theme) -> None:
        self._themes[theme.theme_id] = theme

    def list_ids(self) -> list[str]:
        return list(self._themes.keys())

    def summaries(self) -> list[dict[str, Any]]:
        out = []
        for t in self._themes.values():
            out.append({
                "theme_id": t.theme_id, "name": t.name, "family": t.family,
                "mode": t.mode, "description": t.description,
                "primary": t.tokens.primary, "accent": t.tokens.accent,
                "background": t.tokens.background,
            })
        return out


class LayoutRegistry:
    def __init__(self) -> None:
        self._layouts: dict[str, LayoutRecipe] = dict(BUILTIN_LAYOUTS)

    def get(self, layout_id: str | None) -> LayoutRecipe:
        if layout_id and layout_id in self._layouts:
            return self._layouts[layout_id]
        return self._layouts[DEFAULT_LAYOUT_ID]

    def has(self, layout_id: str) -> bool:
        return layout_id in self._layouts

    def list_ids(self) -> list[str]:
        return list(self._layouts.keys())

    def summaries(self) -> list[dict[str, Any]]:
        return [{
            "id": r.id, "name": r.name, "category": r.category,
            "description": r.description,
            "slots": [{"id": s.id, "role": s.role.value, "required": s.required,
                       "repeatable": s.repeatable, "max_count": s.max_count}
                      for s in r.slots],
        } for r in self._layouts.values()]


_theme_registry: ThemeRegistry | None = None
_layout_registry: LayoutRegistry | None = None


def get_theme_registry() -> ThemeRegistry:
    global _theme_registry
    if _theme_registry is None:
        _theme_registry = ThemeRegistry()
    return _theme_registry


def get_layout_registry() -> LayoutRegistry:
    global _layout_registry
    if _layout_registry is None:
        _layout_registry = LayoutRegistry()
    return _layout_registry
