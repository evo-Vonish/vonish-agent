"""VonishAgent PPT Artifact Engine.

Deterministic presentation pipeline:

    DeckDesignSpec -> SlideIR -> PPTX + PNG previews -> ValidationReport

Public entry points are re-exported here so callers only import from
``ppt_engine``. The model authors a DeckDesignSpec (theme + layout + content)
and the engine owns all geometry, colour, and typography.
"""
from __future__ import annotations

from .schema import (  # noqa: F401
    SCHEMA_VERSION,
    DeckDesignSpec,
    DeckResult,
    ElementPatch,
    SlideContent,
    SlideIR,
    SlideSpec,
    Theme,
    ValidationReport,
    ValidatorIssue,
)

__all__ = [
    "SCHEMA_VERSION",
    "DeckDesignSpec",
    "DeckResult",
    "ElementPatch",
    "SlideContent",
    "SlideIR",
    "SlideSpec",
    "Theme",
    "ValidationReport",
    "ValidatorIssue",
    "generate_deck",
    "build_deck_spec",
    "get_theme_registry",
    "get_layout_registry",
]


def generate_deck(*args, **kwargs):
    """Lazy proxy to ``ppt_engine.engine.generate_deck``."""
    from .engine import generate_deck as _impl
    return _impl(*args, **kwargs)


def build_deck_spec(*args, **kwargs):
    from .builder import build_deck_spec as _impl
    return _impl(*args, **kwargs)


def get_theme_registry():
    from .registry import get_theme_registry as _impl
    return _impl()


def get_layout_registry():
    from .registry import get_layout_registry as _impl
    return _impl()
