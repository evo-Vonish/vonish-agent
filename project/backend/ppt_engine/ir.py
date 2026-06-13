"""DeckDesignSpec -> SlideIR.

Bridges the agent-authored spec to deterministic, positioned slide IR by
running each slide's layout recipe through the layout engine.
"""
from __future__ import annotations

from .layouts.engine import render_layout
from .schema import (
    Canvas,
    DeckDesignSpec,
    SlideIR,
    SlideSpec,
    Theme,
)


def build_slide_ir(spec: SlideSpec, index: int, deck_id: str, theme: Theme,
                   canvas: Canvas) -> SlideIR:
    elements, background = render_layout(spec.layout_id, theme, spec.content, canvas)
    return SlideIR(
        deck_id=deck_id,
        slide_id=f"{deck_id}-s{index:02d}",
        slide_index=index,
        layout_id=spec.layout_id,
        theme_id=theme.theme_id,
        canvas=canvas,
        background=background,
        elements=elements,
        notes=spec.notes,
    )


def build_deck_ir(deck: DeckDesignSpec, theme: Theme) -> list[SlideIR]:
    return [
        build_slide_ir(slide, i, deck.deck_id or "deck", theme, deck.canvas)
        for i, slide in enumerate(deck.slides)
    ]
