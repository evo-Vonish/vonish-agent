"""Phase 3 extension interfaces — declared, not implemented.

These are real, importable abstract interfaces so downstream code can depend on
the *shape* of future capabilities today, and so the roadmap is honest about
what is a stub. Each method raises ``NotImplementedError`` — none of these are
wired into the main delivery chain, by design (the brief: do not push unstable
Phase 3 features into the main pipeline).

Implement order (per the research report):
  1. ScreenshotInspector / VisualReviewProvider  (render -> observe loop)
  2. VlmDesignJudge                              (MLLM design scoring)
  3. ReferenceDeckAnalyzer                       (learn style from a sample .pptx)
  4. SvgIntermediateRenderer                     (SVG -> DrawingML)
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from .schema import SlideIR, ValidatorIssue


@dataclass
class VisualReview:
    score: float = 0.0                  # 1-5
    dimension: str = ""                 # aesthetics | readability | consistency | hierarchy
    notes: str = ""
    issues: list[ValidatorIssue] = field(default_factory=list)


class ScreenshotInspector(abc.ABC):
    """Phase 3: render a slide to pixels for environment-grounded reflection.

    The Phase 1 Pillow preview already gives us pixels; a Phase 3 inspector
    would add OCR round-trip checks and image-quality metrics (Laplacian
    blur, colour-histogram drift vs theme)."""

    @abc.abstractmethod
    def inspect(self, slide: SlideIR, png_path: str) -> dict[str, Any]:
        raise NotImplementedError("ScreenshotInspector is a Phase 3 stub")


class VisualReviewProvider(abc.ABC):
    """Phase 3: L2 screenshot-analysis review layer."""

    @abc.abstractmethod
    def review(self, slide: SlideIR, png_path: str) -> VisualReview:
        raise NotImplementedError("VisualReviewProvider is a Phase 3 stub")


class VlmDesignJudge(abc.ABC):
    """Phase 3: L3 MLLM visual judgement (PPTEval-style 3 dimensions)."""

    @abc.abstractmethod
    def judge(self, png_path: str, *, dimensions: list[str]) -> list[VisualReview]:
        raise NotImplementedError("VlmDesignJudge is a Phase 3 stub")


class ReferenceDeckAnalyzer(abc.ABC):
    """Phase 3: learn theme/layout from a user-supplied reference .pptx."""

    @abc.abstractmethod
    def analyze(self, pptx_path: str) -> dict[str, Any]:
        raise NotImplementedError("ReferenceDeckAnalyzer is a Phase 3 stub")


class SvgIntermediateRenderer(abc.ABC):
    """Phase 3: SVG visual middle-layer -> native DrawingML."""

    @abc.abstractmethod
    def slide_to_svg(self, slide: SlideIR) -> str:
        raise NotImplementedError("SvgIntermediateRenderer is a Phase 3 stub")

    @abc.abstractmethod
    def svg_to_drawingml(self, svg: str) -> bytes:
        raise NotImplementedError("SvgIntermediateRenderer is a Phase 3 stub")


__all__ = [
    "VisualReview", "ScreenshotInspector", "VisualReviewProvider",
    "VlmDesignJudge", "ReferenceDeckAnalyzer", "SvgIntermediateRenderer",
]
