"""Deterministic text measurement for overflow detection and auto-fit.

The renderer (python-pptx) and the preview (Pillow) both need to know whether a
string fits a box *before* anything is drawn — that is what lets the Validator
catch ``TEXT_OVERFLOW`` and the layout engine auto-fit font sizes.

We use a character-width heuristic instead of depending on a specific installed
font. This is deterministic (stable across machines and CI) and CJK-aware,
which matters because the decks are bilingual. Font sizes are points; geometry
is pixels (1pt = 96/72 px).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from .schema import PX_PER_PT

# Shared text-box insets (px). The layout auto-fit, the validator overflow
# check, and the python-pptx / Pillow renderers all use these so geometry is
# consistent across the pipeline.
TEXT_INSET_X = 10.0
TEXT_INSET_Y = 6.0


def line_px(font_pt: float, line_height: float = 1.35) -> float:
    """Height of one line at *font_pt* points, in pixels."""
    return font_pt * PX_PER_PT * line_height


def _is_wide(ch: str) -> bool:
    """True for full-width CJK / kana / wide punctuation."""
    if ch in "　":
        return True
    try:
        return unicodedata.east_asian_width(ch) in ("W", "F")
    except Exception:
        return False


def char_width_px(ch: str, font_px: float) -> float:
    """Approximate advance width of one character at *font_px* pixels."""
    if ch == "\t":
        return font_px * 2.0
    if ch == " ":
        return font_px * 0.30
    if _is_wide(ch):
        return font_px * 1.02
    if ch.isupper():
        return font_px * 0.62
    if ch.isdigit():
        return font_px * 0.55
    if ch in "iIl.,:;'!|":
        return font_px * 0.30
    if ch in "mwMW":
        return font_px * 0.85
    return font_px * 0.52


def _token_runs(line: str) -> list[str]:
    """Split a line into wrap units: latin words stay whole, CJK wraps per char."""
    runs: list[str] = []
    buf = ""
    for ch in line:
        if _is_wide(ch) or ch in "，。！？；：、（）【】《》":
            if buf:
                runs.append(buf)
                buf = ""
            runs.append(ch)
        elif ch == " ":
            buf += ch
            runs.append(buf)
            buf = ""
        else:
            buf += ch
    if buf:
        runs.append(buf)
    return runs


@dataclass
class TextMetrics:
    lines: int
    text_width: float          # widest line, px
    text_height: float         # px including line spacing
    line_count_by_wrap: list[int] = field(default_factory=list)
    overflow_x: bool = False
    overflow_y: bool = False


def measure_text(
    text: str,
    font_pt: float,
    max_width_px: float,
    *,
    line_height: float = 1.35,
    max_height_px: float | None = None,
    bold: bool = False,
) -> TextMetrics:
    """Wrap *text* into *max_width_px* and report dimensions.

    Honours explicit newlines. Bold adds a small width penalty.
    """
    font_px = max(1.0, font_pt * PX_PER_PT)
    bold_factor = 1.06 if bold else 1.0
    usable = max(1.0, max_width_px)

    total_lines = 0
    widest = 0.0
    per_paragraph: list[int] = []

    for paragraph in (text or "").split("\n"):
        if paragraph == "":
            total_lines += 1
            per_paragraph.append(1)
            continue
        runs = _token_runs(paragraph)
        cur_w = 0.0
        para_lines = 1
        for run in runs:
            run_w = sum(char_width_px(c, font_px) for c in run) * bold_factor
            if run_w > usable and cur_w == 0.0:
                # A single run wider than the box: it occupies (and overflows) a line.
                widest = max(widest, run_w)
                para_lines += 0
                cur_w = 0.0
                total_lines_extra = int(run_w // usable)
                para_lines += total_lines_extra
                continue
            if cur_w + run_w > usable and cur_w > 0.0:
                para_lines += 1
                widest = max(widest, cur_w)
                cur_w = run_w if run.strip() != "" else 0.0
            else:
                cur_w += run_w
        widest = max(widest, cur_w)
        total_lines += para_lines
        per_paragraph.append(para_lines)

    # One line needs ascent+descent (~1.16 em); each *extra* line adds full
    # leading. This matches rendered text far better than lines*lineHeight and
    # avoids false overflow on short single-line labels.
    leading = font_px * line_height
    single = font_px * 1.16
    text_height = single + max(0, total_lines - 1) * leading
    metrics = TextMetrics(
        lines=total_lines,
        text_width=round(widest, 2),
        text_height=round(text_height, 2),
        line_count_by_wrap=per_paragraph,
        overflow_x=widest > usable + 0.5,
    )
    if max_height_px is not None:
        metrics.overflow_y = text_height > max_height_px + 0.5
    return metrics


def measure_in_box(
    text: str,
    font_pt: float,
    box_width_px: float,
    box_height_px: float,
    *,
    line_height: float = 1.35,
    bold: bool = False,
) -> TextMetrics:
    """Measure *text* against a box, applying the shared insets."""
    inner_w = max(1.0, box_width_px - 2 * TEXT_INSET_X)
    inner_h = max(1.0, box_height_px - 2 * TEXT_INSET_Y)
    return measure_text(text, font_pt, inner_w, line_height=line_height,
                        max_height_px=inner_h, bold=bold)


def fit_font_size(
    text: str,
    box_width_px: float,
    box_height_px: float,
    *,
    start_pt: float,
    min_pt: float,
    line_height: float = 1.35,
    bold: bool = False,
    pad_px: float | None = None,
) -> tuple[float, TextMetrics]:
    """Largest font size in [min_pt, start_pt] that fits the box (else min_pt)."""
    size = round(start_pt, 1)
    last: TextMetrics | None = None
    while size >= min_pt:
        m = measure_in_box(text, size, box_width_px, box_height_px,
                           line_height=line_height, bold=bold)
        last = m
        if not m.overflow_x and not m.overflow_y:
            return round(size, 1), m
        size -= 1.0
    return round(min_pt, 1), (last or measure_in_box(
        text, min_pt, box_width_px, box_height_px,
        line_height=line_height, bold=bold))
