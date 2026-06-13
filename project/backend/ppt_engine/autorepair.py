"""Auto-repair loop.

generate -> validate -> auto-fix the fixable issues -> re-validate, up to N
rounds. Only ``fix_strategy == AUTO`` issues are touched; AGENT/USER issues are
reported, never silently "fixed". If blocking errors survive all rounds the
report says so (``deliverable = False``) — nothing is faked.
"""
from __future__ import annotations

from .schema import (
    FixStrategy,
    IssueType,
    SlideElement,
    SlideIR,
    Theme,
    ValidationReport,
)
from .text_metrics import fit_font_size
from .validator import PptValidator, contrast_ratio


def _find(slides: list[SlideIR], slide_index: int, element_id: str) -> SlideElement | None:
    for ir in slides:
        if ir.slide_index != slide_index:
            continue
        for el in ir.all_elements():
            if el.element_id == element_id:
                return el
    return None


def _canvas(slides, slide_index):
    for ir in slides:
        if ir.slide_index == slide_index:
            return ir.canvas, ir
    return None, None


def apply_auto_fixes(slides: list[SlideIR], theme: Theme, report: ValidationReport) -> int:
    """Mutate the SlideIR to resolve AUTO-fixable issues. Returns count applied."""
    fixed = 0
    palette = theme.tokens.palette()
    for issue in report.issues:
        if issue.fix_strategy != FixStrategy.AUTO or not issue.suggested_fix:
            continue
        action = issue.suggested_fix.action
        params = issue.suggested_fix.parameters
        el = _find(slides, issue.slide_index, issue.element_id) if issue.element_id else None

        if action == "reduce_font_size" and el and el.text_style:
            new_size, _ = fit_font_size(
                el.text, el.bbox.width, el.bbox.height,
                start_pt=el.text_style.fontSize,
                min_pt=max(8.0, params.get("min_pt", el.text_style.fontSize * 0.6)),
                line_height=el.text_style.lineHeight, bold=el.text_style.bold)
            if new_size < el.text_style.fontSize:
                el.text_style.fontSize = new_size
                issue.auto_fixed = True
                fixed += 1

        elif action == "clamp_to_canvas" and el:
            cv, _ = _canvas(slides, issue.slide_index)
            if cv:
                _clamp(el, 0, 0, cv.width, cv.height)
                issue.auto_fixed = True
                fixed += 1

        elif action == "nudge_inside_margin" and el:
            cv, _ = _canvas(slides, issue.slide_index)
            if cv:
                m = theme.layout_rules.safeMargin
                _clamp(el, cv.width * m.left * 0.5, cv.height * m.top * 0.5,
                       cv.width * (1 - m.right * 0.5), cv.height * (1 - m.bottom * 0.5))
                issue.auto_fixed = True
                fixed += 1

        elif action == "raise_font_size" and el and el.text_style:
            target = params.get("target", 12.0)
            from .text_metrics import measure_in_box
            mm = measure_in_box(el.text, target, el.bbox.width, el.bbox.height,
                                line_height=el.text_style.lineHeight, bold=el.text_style.bold)
            if not (mm.overflow_x or mm.overflow_y):
                el.text_style.fontSize = target
                issue.auto_fixed = True
                fixed += 1

        elif action == "map_to_theme_color" and el:
            frm, to = params.get("from"), params.get("to")
            if frm and to:
                _swap_color(el, frm, to)
                issue.auto_fixed = True
                fixed += 1

        elif action == "fix_contrast" and el and el.text_style:
            bg = params.get("bg", theme.tokens.background)
            need = params.get("need", 4.5)
            candidates = [theme.tokens.text, theme.tokens.textInverse,
                          theme.tokens.textMuted, "#FFFFFF", "#0F172A"]
            best = max(candidates, key=lambda c: contrast_ratio(c, bg))
            if contrast_ratio(best, bg) >= need or contrast_ratio(best, bg) > contrast_ratio(el.text_style.color, bg):
                el.text_style.color = best
                issue.auto_fixed = True
                fixed += 1

        elif action == "unify_fonts":
            cv, ir = _canvas(slides, issue.slide_index)
            if ir:
                for e in ir.all_elements():
                    if e.text_style:
                        if e.text_style.role == "code":
                            continue
                        e.text_style.fontFamily = (
                            theme.fonts.heading_primary() if e.text_style.role == "heading"
                            else theme.fonts.body_primary())
                issue.auto_fixed = True
                fixed += 1
    return fixed


def _clamp(el: SlideElement, x0, y0, x1, y1) -> None:
    b = el.bbox
    w = min(b.width, x1 - x0)
    h = min(b.height, y1 - y0)
    nx = min(max(b.x, x0), x1 - w)
    ny = min(max(b.y, y0), y1 - h)
    b.x, b.y, b.width, b.height = nx, ny, w, h


def _swap_color(el: SlideElement, frm: str, to: str) -> None:
    frm_l = frm.lower()
    if el.text_style and el.text_style.color.lower() == frm_l:
        el.text_style.color = to
    if el.shape_style:
        if el.shape_style.fill and el.shape_style.fill.lower() == frm_l:
            el.shape_style.fill = to
        if el.shape_style.stroke and el.shape_style.stroke.lower() == frm_l:
            el.shape_style.stroke = to


def repair_loop(slides: list[SlideIR], theme: Theme, *, max_rounds: int = 3
                ) -> tuple[ValidationReport, int]:
    """Validate + auto-fix until stable or max rounds. Returns (final_report, rounds)."""
    report = PptValidator(theme).validate(slides)
    rounds = 0
    total_applied = 0
    while rounds < max_rounds:
        auto_issues = [i for i in report.issues if i.fix_strategy == FixStrategy.AUTO]
        if not auto_issues:
            break
        applied = apply_auto_fixes(slides, theme, report)
        rounds += 1
        total_applied += applied
        report = PptValidator(theme).validate(slides)
        report.repair_rounds = rounds
        if applied == 0:
            break
    report.repair_rounds = rounds
    report.summary.auto_fixed = total_applied  # cumulative across rounds
    return report, rounds
