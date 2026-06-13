"""Visual QA — L2 image-grounded checks on the rendered PNG previews.

This is the L2 layer from the design report, grounded in the actual rendered
pixels (not the IR). It runs on the same Pillow previews the engine already
produces, so it needs no headless Office and no extra services. OCR is *not*
claimed here (tesseract is not a dependency); instead text presence is checked
by foreground-ink analysis, which deterministically catches a text box that
failed to render at all.

Concrete implementations of the previously-abstract ``ScreenshotInspector`` and
``VisualReviewProvider`` interfaces live here, turning those Phase-3 stubs into
working L2 components. ``VlmDesignJudge`` / ``ReferenceDeckAnalyzer`` /
``SvgIntermediateRenderer`` remain reserved.

L2 is opt-in (``generate_deck(..., visual_qa=True)``): it is image analysis, a
bit slower than the L1 rules, and off the fast path by default — but fully
implemented and tested.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .interfaces import ScreenshotInspector, VisualReview, VisualReviewProvider
from .schema import (
    FixStrategy,
    IssueType,
    Severity,
    SlideIR,
    SuggestedFix,
    Theme,
    ValidatorIssue,
    VisualFinding,
)
from .validator import color_distance

# thresholds tuned so clean engine output produces zero findings
BLANK_STD_MIN = 4.0          # grayscale stddev below this => essentially blank
SHARPNESS_MIN = 3.0          # Laplacian variance below this => blurry
COLOR_DRIFT_DIST = 80.0      # prominent fill > this from every palette colour
COLOR_DRIFT_COVER = 0.03     # only judge colours covering >3% of the slide
TEXT_INK_MIN = 0.004         # foreground-ink fraction in a text box


def _load_rgb(png_path: str | Path) -> np.ndarray:
    with Image.open(str(png_path)) as im:
        return np.asarray(im.convert("RGB"), dtype=np.float64)


def _grayscale(rgb: np.ndarray) -> np.ndarray:
    return rgb @ np.array([0.299, 0.587, 0.114])


def _laplacian_variance(gray: np.ndarray) -> float:
    # 4-neighbour Laplacian via array shifts (no scipy dependency)
    lap = (-4.0 * gray
           + np.roll(gray, 1, 0) + np.roll(gray, -1, 0)
           + np.roll(gray, 1, 1) + np.roll(gray, -1, 1))
    inner = lap[1:-1, 1:-1]
    return float(inner.var())


def _prominent_colors(rgb: np.ndarray, bins: int = 6) -> list[tuple[tuple[int, int, int], float]]:
    """Coarse colour histogram -> [(rgb, coverage_fraction)] sorted desc."""
    h, w, _ = rgb.shape
    q = (rgb / 256.0 * bins).astype(np.int64)
    flat = q.reshape(-1, 3)
    keys = flat[:, 0] * bins * bins + flat[:, 1] * bins + flat[:, 2]
    counts = np.bincount(keys, minlength=bins ** 3)
    total = h * w
    out: list[tuple[tuple[int, int, int], float]] = []
    for k in np.argsort(counts)[::-1]:
        c = counts[k]
        if c == 0:
            break
        cover = c / total
        if cover < 0.005:
            break
        r = (k // (bins * bins)) % bins
        g = (k // bins) % bins
        b = k % bins
        step = 256 // bins
        out.append((((r * step + step // 2), (g * step + step // 2), (b * step + step // 2)), cover))
    return out


def _to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % rgb


class PillowScreenshotInspector(ScreenshotInspector):
    """Concrete L2 inspector: pixel metrics for one rendered slide."""

    def inspect(self, slide: SlideIR, png_path: str) -> dict[str, Any]:
        rgb = _load_rgb(png_path)
        gray = _grayscale(rgb)
        return {
            "std": float(gray.std()),
            "sharpness": _laplacian_variance(gray),
            "prominent": _prominent_colors(rgb),
            "shape": rgb.shape,
            "rgb": rgb,
        }

    def text_ink_fraction(self, rgb: np.ndarray, bbox_px, canvas, bg_rgb) -> float:
        """Fraction of a text box's pixels that differ from the background."""
        h, w, _ = rgb.shape
        sx, sy = w / canvas.width, h / canvas.height
        x0 = max(0, int(bbox_px[0] * sx)); y0 = max(0, int(bbox_px[1] * sy))
        x1 = min(w, int((bbox_px[0] + bbox_px[2]) * sx)); y1 = min(h, int((bbox_px[1] + bbox_px[3]) * sy))
        if x1 <= x0 or y1 <= y0:
            return 1.0
        region = rgb[y0:y1, x0:x1]
        bg = np.array(bg_rgb, dtype=np.float64)
        dist = np.sqrt(((region - bg) ** 2).sum(axis=2))
        return float((dist > 45.0).mean())


class RuleVisualReviewProvider(VisualReviewProvider):
    """Concrete L2 review: turn inspector metrics into a 1-5 readability score."""

    def __init__(self) -> None:
        self._inspector = PillowScreenshotInspector()

    def review(self, slide: SlideIR, png_path: str) -> VisualReview:
        m = self._inspector.inspect(slide, png_path)
        std, sharp = m["std"], m["sharpness"]
        score = 5.0
        notes = []
        if std < BLANK_STD_MIN:
            score -= 3.0
            notes.append("near-blank render")
        if sharp < SHARPNESS_MIN:
            score -= 1.0
            notes.append("low edge sharpness")
        return VisualReview(score=max(1.0, score), dimension="readability",
                            notes="; ".join(notes) or "ok")


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def run_visual_qa(
    slides: list[SlideIR],
    png_abs_paths: list[str],
    theme: Theme,
) -> tuple[list[VisualFinding], list[ValidatorIssue]]:
    """Run L2 checks over rendered slides. Returns (findings, image issues)."""
    inspector = PillowScreenshotInspector()
    palette = [_hex_to_rgb(c) for c in theme.tokens.palette()]
    findings: list[VisualFinding] = []
    issues: list[ValidatorIssue] = []
    counter = 0

    def issue(**kw) -> ValidatorIssue:
        nonlocal counter
        counter += 1
        kw.setdefault("id", f"vqa-{counter:03d}")
        return ValidatorIssue(**kw)

    for ir, png in zip(slides, png_abs_paths):
        if not Path(png).exists():
            continue
        m = inspector.inspect(ir, png)
        rgb = m["rgb"]
        std, sharp = m["std"], m["sharpness"]
        bg_rgb = _hex_to_rgb(ir.background.color)

        # blankness
        blank_ok = std >= BLANK_STD_MIN
        findings.append(VisualFinding(slide_index=ir.slide_index, metric="blankness",
                                      score=round(std, 2), ok=blank_ok,
                                      detail=f"grayscale stddev {std:.1f}"))
        if not blank_ok:
            issues.append(issue(type=IssueType.RENDERED_BLANK, severity=Severity.ERROR,
                                slide_id=ir.slide_id, slide_index=ir.slide_index,
                                message=f"Slide renders nearly blank (stddev {std:.1f})",
                                fixable=False, fix_strategy=FixStrategy.AGENT,
                                suggested_fix=SuggestedFix(action="re_render_or_add_content")))

        # sharpness
        sharp_ok = sharp >= SHARPNESS_MIN
        findings.append(VisualFinding(slide_index=ir.slide_index, metric="sharpness",
                                      score=round(sharp, 2), ok=sharp_ok,
                                      detail=f"laplacian variance {sharp:.1f}"))
        if not sharp_ok and blank_ok:
            issues.append(issue(type=IssueType.IMAGE_BLURRY, severity=Severity.WARNING,
                                slide_id=ir.slide_id, slide_index=ir.slide_index,
                                message=f"Low edge sharpness ({sharp:.1f}) — possible blur",
                                fixable=False, fix_strategy=FixStrategy.AGENT,
                                suggested_fix=SuggestedFix(action="check_raster_assets")))

        # colour drift: a high-coverage fill far from every theme colour
        worst_drift = 0.0
        worst_hex = ""
        for color, cover in m["prominent"]:
            if cover < COLOR_DRIFT_COVER:
                continue
            d = min((color_distance(_to_hex(color), _to_hex(p)) for p in palette), default=0.0)
            if d > worst_drift:
                worst_drift, worst_hex = d, _to_hex(color)
        drift_ok = worst_drift <= COLOR_DRIFT_DIST
        findings.append(VisualFinding(slide_index=ir.slide_index, metric="color_drift",
                                      score=round(worst_drift, 1), ok=drift_ok,
                                      detail=f"worst prominent colour {worst_hex} dist {worst_drift:.0f}"))
        if not drift_ok:
            issues.append(issue(type=IssueType.COLOR_DRIFT, severity=Severity.WARNING,
                                slide_id=ir.slide_id, slide_index=ir.slide_index,
                                message=f"Rendered colour {worst_hex} drifts {worst_drift:.0f} from theme",
                                current_value={"color": worst_hex},
                                fixable=False, fix_strategy=FixStrategy.AGENT))

        # text presence: each non-empty text element should have foreground ink
        missing = 0
        for el in ir.all_elements():
            if el.type.value != "text" or not (el.text or "").strip():
                continue
            if el.role.value in ("accent_bar", "decoration", "background"):
                continue
            frac = inspector.text_ink_fraction(rgb, el.bbox.as_list(), ir.canvas, bg_rgb)
            if frac < TEXT_INK_MIN:
                missing += 1
        text_ok = missing == 0
        findings.append(VisualFinding(slide_index=ir.slide_index, metric="text_presence",
                                      score=float(missing), ok=text_ok,
                                      detail=f"{missing} text box(es) without rendered ink"))
        if not text_ok:
            issues.append(issue(type=IssueType.RENDER_TEXT_MISSING, severity=Severity.ERROR,
                                slide_id=ir.slide_id, slide_index=ir.slide_index,
                                message=f"{missing} text element(s) did not render visible text",
                                fixable=False, fix_strategy=FixStrategy.AGENT,
                                suggested_fix=SuggestedFix(action="check_font_or_contrast")))

    return findings, issues
