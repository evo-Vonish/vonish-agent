"""PptValidator — deterministic quality gate over SlideIR.

Runs the L1 rule layer from the design report: overflow, out-of-bounds, unsafe
margin, small font, long title, empty/overcrowded slide, off-theme colour, low
contrast (WCAG), font chaos, element overlap. Produces a structured
``ValidationReport`` with per-issue ``suggested_fix`` so the auto-repair loop
can act on it. Geometry checks reuse the same text metrics as the layout
engine, so what the validator sees is what the renderer drew.
"""
from __future__ import annotations

from .schema import (
    BBox,
    ElementRole,
    FixStrategy,
    IssueType,
    Severity,
    SlideElement,
    SlideIR,
    SuggestedFix,
    Theme,
    ValidationReport,
    ValidationSummary,
    ValidatorIssue,
)
from .text_metrics import measure_in_box

# roles that are decorative / engine-controlled and exempt from some checks
_DECOR_ROLES = {ElementRole.ACCENTBAR, ElementRole.DECORATION, ElementRole.BACKGROUND}
_STRUCTURAL_ROLES = {
    ElementRole.CARD, ElementRole.STEP, ElementRole.DIAGRAM, ElementRole.CHART,
    ElementRole.LEGEND, ElementRole.CODE, ElementRole.FOOTER, ElementRole.IMAGE,
}
_HEADING_ROLES = {ElementRole.TITLE, ElementRole.SUBTITLE, ElementRole.CARD_TITLE,
                  ElementRole.QUOTE, ElementRole.BADGE}


# ---------------------------------------------------------------------------
# colour utilities
# ---------------------------------------------------------------------------
def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = (hex_color or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (0, 0, 0)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (0, 0, 0)


def _rel_luminance(hex_color: str) -> float:
    def chan(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(hex_color)
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast_ratio(fg: str, bg: str) -> float:
    l1, l2 = _rel_luminance(fg), _rel_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def color_distance(a: str, b: str) -> float:
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    return ((ra - rb) ** 2 + (ga - gb) ** 2 + (ba - bb) ** 2) ** 0.5


def nearest_theme_color(color: str, palette: list[str]) -> str:
    if not palette:
        return color
    return min(palette, key=lambda c: color_distance(color, c))


# ---------------------------------------------------------------------------
class PptValidator:
    def __init__(self, theme: Theme):
        self.theme = theme
        self.tk = theme.tokens
        self.cons = theme.constraints
        self.palette = set(self.tk.palette())
        self._counter = 0

    def _issue(self, **kw) -> ValidatorIssue:
        self._counter += 1
        kw.setdefault("id", f"iss-{self._counter:03d}")
        return ValidatorIssue(**kw)

    # -- public ------------------------------------------------------------
    def validate(self, slides: list[SlideIR]) -> ValidationReport:
        issues: list[ValidatorIssue] = []
        for ir in slides:
            issues.extend(self._validate_slide(ir))
        return self._report(slides, issues)

    # -- per slide ---------------------------------------------------------
    def _validate_slide(self, ir: SlideIR) -> list[ValidatorIssue]:
        out: list[ValidatorIssue] = []
        elements = ir.all_elements()
        cw, ch = ir.canvas.width, ir.canvas.height
        m = self.theme.layout_rules.safeMargin
        safe = BBox(x=cw * m.left * 0.5, y=ch * m.top * 0.5,
                    width=cw * (1 - (m.left + m.right) * 0.5),
                    height=ch * (1 - (m.top + m.bottom) * 0.5))
        fonts_seen: set[str] = set()
        text_chars = 0

        for el in elements:
            self._check_bounds(ir, el, cw, ch, safe, out)
            if el.type.value == "text" and el.text_style and el.text.strip():
                text_chars += len(el.text.strip())
                # A mono code font is a legitimate 3rd family (serif heading +
                # sans body + mono code), so don't count it toward font chaos.
                if el.text_style.role != "code":
                    fonts_seen.add(el.text_style.fontFamily)
                self._check_overflow(ir, el, out)
                self._check_font_size(ir, el, out)
                self._check_title_length(ir, el, out)
                self._check_contrast(ir, el, elements, out)
            self._check_color_theme(ir, el, out)

        self._check_empty(ir, text_chars, elements, out)
        self._check_font_chaos(ir, fonts_seen, out)
        self._check_overcrowded(ir, elements, out)
        self._check_overlap(ir, elements, out)
        return out

    # -- individual rules --------------------------------------------------
    def _check_overflow(self, ir, el, out):
        ts = el.text_style
        m = measure_in_box(el.text, ts.fontSize, el.bbox.width, el.bbox.height,
                           line_height=ts.lineHeight, bold=ts.bold)
        # tolerance: a few px / 8% to avoid rounding noise
        over_y = m.text_height > el.bbox.height - 2 * 6 + max(6.0, el.bbox.height * 0.04)
        over_x = m.overflow_x
        if over_y or over_x:
            out.append(self._issue(
                type=IssueType.TEXT_OVERFLOW, severity=Severity.ERROR,
                slide_id=ir.slide_id, slide_index=ir.slide_index,
                element_id=el.element_id, element_role=el.role.value,
                message=(f"Text overflows its box ({'height' if over_y else 'width'}); "
                         f"{m.lines} lines at {ts.fontSize}pt"),
                current_value={"fontSize": ts.fontSize, "lines": m.lines,
                               "box": el.bbox.as_list()},
                fixable=True, fix_strategy=FixStrategy.AUTO,
                suggested_fix=SuggestedFix(action="reduce_font_size",
                                           parameters={"min_pt": ts.fontSize * 0.6})))

    def _check_bounds(self, ir, el, cw, ch, safe, out):
        if el.role in _DECOR_ROLES or el.type.value == "group":
            return
        b = el.bbox
        if b.x < -0.5 or b.y < -0.5 or b.x2 > cw + 0.5 or b.y2 > ch + 0.5:
            out.append(self._issue(
                type=IssueType.OUT_OF_BOUNDS, severity=Severity.ERROR,
                slide_id=ir.slide_id, slide_index=ir.slide_index,
                element_id=el.element_id, element_role=el.role.value,
                message="Element extends beyond the slide canvas",
                current_value={"bbox": b.as_list(), "canvas": [cw, ch]},
                fixable=True, fix_strategy=FixStrategy.AUTO,
                suggested_fix=SuggestedFix(action="clamp_to_canvas")))
        elif b.x < safe.x - 0.5 or b.y < safe.y - 0.5 or b.x2 > safe.x2 + 0.5 or b.y2 > safe.y2 + 0.5:
            out.append(self._issue(
                type=IssueType.UNSAFE_MARGIN, severity=Severity.WARNING,
                slide_id=ir.slide_id, slide_index=ir.slide_index,
                element_id=el.element_id, element_role=el.role.value,
                message="Element crosses the safe margin",
                current_value={"bbox": b.as_list()},
                fixable=True, fix_strategy=FixStrategy.AUTO,
                suggested_fix=SuggestedFix(action="nudge_inside_margin")))

    def _check_font_size(self, ir, el, out):
        if el.role in _DECOR_ROLES:
            return
        size = el.text_style.fontSize
        if size < 12.0:
            out.append(self._issue(
                type=IssueType.FONT_TOO_SMALL, severity=Severity.WARNING,
                slide_id=ir.slide_id, slide_index=ir.slide_index,
                element_id=el.element_id, element_role=el.role.value,
                message=f"Font size {size}pt is below the 12pt minimum",
                current_value={"fontSize": size},
                fixable=True, fix_strategy=FixStrategy.AUTO,
                suggested_fix=SuggestedFix(action="raise_font_size",
                                           parameters={"target": 12.0})))

    def _check_title_length(self, ir, el, out):
        if el.role != ElementRole.TITLE:
            return
        if len(el.text.strip()) > self.cons.maxTitleLength:
            out.append(self._issue(
                type=IssueType.TITLE_TOO_LONG, severity=Severity.WARNING,
                slide_id=ir.slide_id, slide_index=ir.slide_index,
                element_id=el.element_id, element_role=el.role.value,
                message=f"Title is {len(el.text.strip())} chars (max {self.cons.maxTitleLength})",
                current_value={"length": len(el.text.strip())},
                fixable=False, fix_strategy=FixStrategy.AGENT,
                suggested_fix=SuggestedFix(action="shorten_title")))

    def _check_color_theme(self, ir, el, out):
        colors: list[str] = []
        if el.text_style and el.text_style.color:
            colors.append(el.text_style.color)
        if el.shape_style:
            for c in (el.shape_style.fill, el.shape_style.stroke):
                if c:
                    colors.append(c)
        for c in colors:
            # pure white / black are universally safe (always in-theme)
            if c.lower() in ("#ffffff", "#000000", "#fff", "#000"):
                continue
            if c.lower() not in self.palette:
                nearest = nearest_theme_color(c, list(self.palette))
                out.append(self._issue(
                    type=IssueType.COLOR_OUT_OF_THEME, severity=Severity.WARNING,
                    slide_id=ir.slide_id, slide_index=ir.slide_index,
                    element_id=el.element_id, element_role=el.role.value,
                    message=f"Colour {c} is not in theme '{self.theme.theme_id}'",
                    current_value={"color": c},
                    fixable=True, fix_strategy=FixStrategy.AUTO,
                    suggested_fix=SuggestedFix(action="map_to_theme_color",
                                               parameters={"from": c, "to": nearest})))

    def _backdrop_for(self, el: SlideElement, elements: list[SlideElement], ir: SlideIR) -> str:
        """Fill colour visible behind a text element (containing shape, else bg)."""
        cx, cy = el.bbox.x + el.bbox.width / 2, el.bbox.y + el.bbox.height / 2
        best = None
        for other in elements:
            if other is el or other.type.value not in ("shape",):
                continue
            if not other.shape_style or not other.shape_style.fill:
                continue
            b = other.bbox
            if b.x <= cx <= b.x2 and b.y <= cy <= b.y2 and other.z_index < el.z_index:
                if best is None or other.z_index > best.z_index:
                    best = other
        if best and best.shape_style and best.shape_style.fill:
            return best.shape_style.fill
        return ir.background.color

    def _check_contrast(self, ir, el, elements, out):
        if el.role in _DECOR_ROLES:
            return
        fg = el.text_style.color
        bg = self._backdrop_for(el, elements, ir)
        ratio = contrast_ratio(fg, bg)
        # WCAG: large text (>=18pt bold, or >=24pt) needs only 3:1, else 4.5:1.
        ts = el.text_style
        large = (ts.fontSize >= 18 and ts.bold) or ts.fontSize >= 24
        need = 3.0 if (large or el.role in _HEADING_ROLES) else 4.5
        if ratio < need:
            out.append(self._issue(
                type=IssueType.LOW_CONTRAST, severity=Severity.WARNING,
                slide_id=ir.slide_id, slide_index=ir.slide_index,
                element_id=el.element_id, element_role=el.role.value,
                message=f"Contrast {ratio:.2f}:1 below {need}:1 on {bg}",
                current_value={"fg": fg, "bg": bg, "ratio": round(ratio, 2)},
                fixable=True, fix_strategy=FixStrategy.AUTO,
                suggested_fix=SuggestedFix(action="fix_contrast",
                                           parameters={"bg": bg, "need": need})))

    def _check_empty(self, ir, text_chars, elements, out):
        meaningful = [e for e in elements if e.type.value in ("text", "chart", "image")
                      and (e.text.strip() or e.type.value in ("chart", "image"))]
        if text_chars < 8 and len(meaningful) < 2:
            out.append(self._issue(
                type=IssueType.EMPTY_SLIDE, severity=Severity.ERROR,
                slide_id=ir.slide_id, slide_index=ir.slide_index,
                message="Slide has almost no content",
                current_value={"text_chars": text_chars, "elements": len(meaningful)},
                fixable=False, fix_strategy=FixStrategy.AGENT,
                suggested_fix=SuggestedFix(action="add_content")))

    def _check_font_chaos(self, ir, fonts_seen, out):
        if len(fonts_seen) > 2:
            out.append(self._issue(
                type=IssueType.FONT_CHAOS, severity=Severity.WARNING,
                slide_id=ir.slide_id, slide_index=ir.slide_index,
                message=f"{len(fonts_seen)} font families on one slide (max 2)",
                current_value={"fonts": sorted(fonts_seen)},
                fixable=True, fix_strategy=FixStrategy.AUTO,
                suggested_fix=SuggestedFix(action="unify_fonts")))

    def _coverage_ratio(self, ir, elements) -> float:
        # Measure *content ink* (text / chart / image), not container panels —
        # a layout panel filling the content rect is intentional, not crowding.
        cols, rows = 64, 36
        grid = [[False] * cols for _ in range(rows)]
        cw, ch = ir.canvas.width, ir.canvas.height
        for el in elements:
            if el.role in _DECOR_ROLES or el.type.value not in ("text", "chart", "image"):
                continue
            if el.type.value == "text" and not el.text.strip():
                continue
            b = el.bbox
            c0 = max(0, int(b.x / cw * cols)); c1 = min(cols, int(b.x2 / cw * cols) + 1)
            r0 = max(0, int(b.y / ch * rows)); r1 = min(rows, int(b.y2 / ch * rows) + 1)
            for r in range(r0, r1):
                for c in range(c0, c1):
                    grid[r][c] = True
        covered = sum(row.count(True) for row in grid)
        return covered / (cols * rows)

    def _check_overcrowded(self, ir, elements, out):
        ratio = self._coverage_ratio(ir, elements)
        if ratio > 0.80:
            out.append(self._issue(
                type=IssueType.OVERCROWDED_SLIDE, severity=Severity.WARNING,
                slide_id=ir.slide_id, slide_index=ir.slide_index,
                message=f"Content fill ratio {ratio:.0%} exceeds 80% (whitespace too low)",
                current_value={"fill_ratio": round(ratio, 2)},
                fixable=False, fix_strategy=FixStrategy.AGENT,
                suggested_fix=SuggestedFix(action="split_or_trim")))

    def _check_overlap(self, ir, elements, out):
        panels = [e for e in elements if e.type.value in ("shape", "chart")
                  and e.role in _STRUCTURAL_ROLES]
        for i in range(len(panels)):
            for j in range(i + 1, len(panels)):
                a, b = panels[i].bbox, panels[j].bbox
                inter = a.intersection_area(b)
                if inter <= 0:
                    continue
                smaller = min(a.area, b.area) or 1.0
                # ignore containment (one inside the other is intentional nesting)
                contained = inter >= smaller * 0.95
                if not contained and inter > smaller * 0.12:
                    out.append(self._issue(
                        type=IssueType.ELEMENT_OVERLAP, severity=Severity.ERROR,
                        slide_id=ir.slide_id, slide_index=ir.slide_index,
                        element_ids=[panels[i].element_id, panels[j].element_id],
                        message=f"Structural elements overlap by {inter/smaller:.0%}",
                        current_value={"intersection": round(inter, 1)},
                        fixable=False, fix_strategy=FixStrategy.AGENT,
                        suggested_fix=SuggestedFix(action="agent_relayout")))

    # -- report ------------------------------------------------------------
    def _report(self, slides, issues) -> ValidationReport:
        s = ValidationSummary(total_issues=len(issues))
        for i in issues:
            if i.severity == Severity.ERROR:
                s.error_count += 1
            elif i.severity == Severity.WARNING:
                s.warning_count += 1
            else:
                s.info_count += 1
            if i.auto_fixed:
                s.auto_fixed += 1
            if i.fixable and i.fix_strategy == FixStrategy.AUTO:
                s.fixable_auto += 1
            elif i.fix_strategy == FixStrategy.AGENT:
                s.fixable_agent += 1
            elif i.fix_strategy == FixStrategy.USER:
                s.requires_user += 1
        blocking = {IssueType.TEXT_OVERFLOW, IssueType.ELEMENT_OVERLAP,
                    IssueType.OUT_OF_BOUNDS, IssueType.EMPTY_SLIDE}
        unresolved_blocking = [i for i in issues
                               if i.type in blocking and i.severity == Severity.ERROR]
        deliverable = len(unresolved_blocking) == 0
        if s.error_count == 0 and s.warning_count == 0:
            grade = "perfect"
        elif s.error_count == 0 and s.warning_count <= 3:
            grade = "good"
        elif not unresolved_blocking:
            grade = "acceptable"
        else:
            grade = "blocked"
        report = ValidationReport(
            deck_id=slides[0].deck_id if slides else "",
            summary=s, issues=issues, deliverable=deliverable,
            delivery_grade=grade,
            blocking_issue_types=sorted({i.type.value for i in unresolved_blocking}),
        )
        return report


def validate_deck(slides: list[SlideIR], theme: Theme) -> ValidationReport:
    return PptValidator(theme).validate(slides)
