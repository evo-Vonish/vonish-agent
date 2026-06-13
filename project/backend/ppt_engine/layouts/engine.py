"""Layout algorithm: (recipe + theme + content) -> positioned SlideElements.

This is where spatial reasoning lives. The model never sets coordinates; every
x/y/w/h, font size, and colour here is derived from the Theme tokens and the
content. Font sizes auto-fit so text does not overflow its box.
"""
from __future__ import annotations

from typing import Callable

from ..schema import (
    Align,
    BBox,
    Canvas,
    ChartContent,
    ElementRole,
    ElementType,
    ShapeStyle,
    ShapeType,
    SlideBackground,
    SlideContent,
    SlideElement,
    TextStyle,
    Theme,
    VAlign,
)
from ..text_metrics import fit_font_size, line_px
from .recipes import BUILTIN_LAYOUTS


class LayoutBuilder:
    """Helper that builds SlideElements within the safe content rect."""

    def __init__(self, theme: Theme, content: SlideContent, canvas: Canvas):
        self.theme = theme
        self.tk = theme.tokens
        self.typo = theme.typography
        self.rules = theme.layout_rules
        self.content = content
        self.canvas = canvas
        self.W = float(canvas.width)
        self.H = float(canvas.height)
        m = self.rules.safeMargin
        self.cx = self.W * m.left
        self.cy = self.H * m.top
        self.cw = self.W * (1 - m.left - m.right)
        self.ch = self.H * (1 - m.top - m.bottom)
        self._n = 0
        self.elements: list[SlideElement] = []

    # -- ids & fonts -------------------------------------------------------
    def _id(self, role: str) -> str:
        self._n += 1
        return f"el-{role}-{self._n}"

    def heading_font(self) -> str:
        return self.theme.fonts.heading_primary()

    def body_font(self) -> str:
        return self.theme.fonts.body_primary()

    def code_font(self) -> str:
        return self.theme.fonts.code_primary()

    # -- primitives --------------------------------------------------------
    def text(
        self, role: ElementRole, x, y, w, h, text, *,
        size_pt: float, color: str, bold=False, align=Align.LEFT,
        valign=VAlign.TOP, font: str | None = None, kind="body",
        min_pt: float | None = None, autofit=True, z=10,
        line_height: float | None = None,
    ) -> SlideElement:
        font = font or (self.heading_font() if kind == "heading" else
                        self.code_font() if kind == "code" else self.body_font())
        lh = line_height if line_height is not None else self.typo.lineHeight
        min_pt = min_pt or (self.typo.minTitleSize if kind == "heading" else self.typo.minBodySize)
        chosen = size_pt
        if autofit and (text or "").strip():
            chosen, _ = fit_font_size(text, w, h, start_pt=size_pt, min_pt=min_pt,
                                      line_height=lh, bold=bold)
        el = SlideElement(
            element_id=self._id(role.value),
            role=role, type=ElementType.TEXT,
            bbox=BBox(x=x, y=y, width=w, height=h),
            z_index=z, text=text or "",
            text_style=TextStyle(fontSize=chosen, fontFamily=font, color=color,
                                 bold=bold, align=align, valign=valign,
                                 lineHeight=lh, role=kind),
        )
        self.elements.append(el)
        return el

    def shape(
        self, role: ElementRole, x, y, w, h, *, fill=None, stroke=None,
        stroke_w=0.0, radius=0.0, shadow="none", shape_type=ShapeType.ROUNDED_RECT,
        z=5, opacity=1.0,
    ) -> SlideElement:
        el = SlideElement(
            element_id=self._id(role.value),
            role=role, type=ElementType.SHAPE,
            bbox=BBox(x=x, y=y, width=w, height=h),
            z_index=z, shape_type=shape_type,
            shape_style=ShapeStyle(fill=fill, stroke=stroke, strokeWidth=stroke_w,
                                   radius=radius, shadow=shadow, opacity=opacity),
        )
        self.elements.append(el)
        return el

    def background(self) -> SlideBackground:
        return SlideBackground(type="solid", color=self.tk.background)

    # -- composite pieces --------------------------------------------------
    def line_px(self, pt: float) -> float:
        return line_px(pt, self.typo.lineHeight)

    def header(self, title: str, *, accent_bar=True) -> float:
        """Standard slide title at the top of the content rect. Returns body top y."""
        bar_w = 6.0
        title_h = self.line_px(self.typo.titleSize) + 22
        tx = self.cx
        if accent_bar:
            self.shape(ElementRole.ACCENTBAR, self.cx, self.cy + 4, bar_w, title_h - 8,
                       fill=self.tk.accent, radius=3, z=6)
            tx = self.cx + bar_w + 14
        self.text(ElementRole.TITLE, tx, self.cy, self.cw - (tx - self.cx), title_h, title,
                  size_pt=self.typo.titleSize, color=self.tk.text, bold=True,
                  align=Align.LEFT, valign=VAlign.MIDDLE, kind="heading", z=12)
        return self.cy + title_h + 18

    def card(self, x, y, w, h, title: str, body: str, *, accent: str | None = None):
        accent = accent or self.tk.accent
        self.shape(ElementRole.CARD, x, y, w, h, fill=self.tk.surfaceElevated,
                   stroke=self.tk.borderSubtle, stroke_w=1, radius=self.rules.cardRadius,
                   shadow=self.rules.shadowIntensity, z=5)
        self.shape(ElementRole.ACCENTBAR, x, y, w, 4, fill=accent,
                   radius=self.rules.cardRadius, z=6)
        pad = 16.0
        title_h = self.line_px(self.typo.subtitleSize) + 12
        if title:
            self.text(ElementRole.CARD_TITLE, x + pad, y + pad, w - 2 * pad, title_h, title,
                      size_pt=self.typo.subtitleSize, color=self.tk.text, bold=True,
                      kind="heading", min_pt=self.typo.minBodySize, valign=VAlign.TOP, z=11)
        if body:
            body_y = y + pad + (title_h + 6 if title else 0)
            self.text(ElementRole.CARD_BODY, x + pad, body_y, w - 2 * pad,
                      y + h - pad - body_y, body, size_pt=self.typo.bodySize,
                      color=self.tk.textMuted, valign=VAlign.TOP, z=11)


# ---------------------------------------------------------------------------
# Per-layout renderers
# ---------------------------------------------------------------------------
def _cover_center(b: LayoutBuilder) -> None:
    c = b.content
    b.shape(ElementRole.ACCENTBAR, b.W / 2 - 40, b.cy + b.ch * 0.28, 80, 5,
            fill=b.tk.accent, radius=3, z=6)
    b.text(ElementRole.TITLE, b.cx, b.cy + b.ch * 0.32, b.cw, b.ch * 0.30,
           c.title, size_pt=b.typo.maxTitleSize, color=b.tk.text, bold=True,
           align=Align.CENTER, valign=VAlign.MIDDLE, kind="heading",
           min_pt=b.typo.minTitleSize, z=12)
    if c.subtitle:
        b.text(ElementRole.SUBTITLE, b.cx, b.cy + b.ch * 0.62, b.cw, 60, c.subtitle,
               size_pt=b.typo.subtitleSize, color=b.tk.accent, align=Align.CENTER,
               valign=VAlign.MIDDLE, z=11)
    if c.meta:
        b.text(ElementRole.META, b.cx, b.cy + b.ch * 0.82, b.cw, 40, c.meta,
               size_pt=b.typo.captionSize, color=b.tk.textMuted, align=Align.CENTER,
               valign=VAlign.MIDDLE, z=11)


def _toc_simple(b: LayoutBuilder) -> None:
    items = (b.content.items and [i.title or i.body for i in b.content.items]) or b.content.bullets
    items = [s for s in items if (s or "").strip()][:8]
    top = b.header(b.content.title or "目录")
    two_col = len(items) > 4
    col_count = 2 if two_col else 1
    col_w = (b.cw - (20 if two_col else 0)) / col_count
    rows = (len(items) + col_count - 1) // col_count
    avail = b.cy + b.ch - top
    row_h = min(72.0, avail / max(1, rows))
    for idx, item in enumerate(items):
        col = idx // rows if two_col else 0
        row = idx % rows if two_col else idx
        x = b.cx + col * (col_w + 20)
        y = top + row * row_h
        b.shape(ElementRole.BADGE, x, y + row_h / 2 - 16, 32, 32, fill=b.tk.surfaceElevated,
                stroke=b.tk.accent, stroke_w=1.5, radius=16, z=6)
        b.text(ElementRole.BADGE, x, y + row_h / 2 - 16, 32, 32, str(idx + 1),
               size_pt=15, color=b.tk.accent, bold=True, align=Align.CENTER,
               valign=VAlign.MIDDLE, autofit=False, z=12)
        b.text(ElementRole.BULLET, x + 44, y, col_w - 50, row_h, item,
               size_pt=b.typo.bodySize, color=b.tk.text, valign=VAlign.MIDDLE, z=11)


def _chapter_break(b: LayoutBuilder) -> None:
    c = b.content
    num = c.chapter_number or c.meta
    if num:
        b.text(ElementRole.BADGE, b.cx, b.cy, b.cw * 0.5, 120, num,
               size_pt=84, color=b.tk.accent, bold=True, align=Align.LEFT,
               valign=VAlign.TOP, kind="heading", min_pt=40, z=11)
    b.text(ElementRole.TITLE, b.cx, b.cy + b.ch * 0.42, b.cw, b.ch * 0.28,
           c.title, size_pt=b.typo.maxTitleSize, color=b.tk.text, bold=True,
           valign=VAlign.MIDDLE, kind="heading", min_pt=b.typo.minTitleSize, z=12)
    if c.body:
        b.text(ElementRole.BODY, b.cx, b.cy + b.ch * 0.74, b.cw, 70, c.body,
               size_pt=b.typo.subtitleSize, color=b.tk.textMuted, z=11)


def _three_cards(b: LayoutBuilder) -> None:
    cards = [c for c in b.content.cards if (c.title or c.body)][:4]
    if not cards:
        cards = []
    top = b.header(b.content.title or "")
    n = max(1, len(cards))
    gap = 20.0
    card_w = (b.cw - gap * (n - 1)) / n
    card_h = min(b.cy + b.ch - top, 360.0)
    y = top + max(0.0, (b.cy + b.ch - top - card_h) / 2)
    accents = b.tk.chart or [b.tk.accent]
    for i, card in enumerate(cards):
        x = b.cx + i * (card_w + gap)
        b.card(x, y, card_w, card_h, card.title, card.body,
               accent=accents[i % len(accents)])


def _left_right(b: LayoutBuilder) -> None:
    top = b.header(b.content.title or "")
    gap = 28.0
    col_w = (b.cw - gap) / 2
    col_h = b.cy + b.ch - top
    for i, col in enumerate([b.content.left, b.content.right]):
        x = b.cx + i * (col_w + gap)
        accent = b.tk.accent if i == 0 else b.tk.accentSecondary
        b.shape(ElementRole.CARD, x, top, col_w, col_h, fill=b.tk.surface,
                stroke=b.tk.borderSubtle, stroke_w=1, radius=b.rules.cardRadius,
                shadow=b.rules.shadowIntensity, z=5)
        b.shape(ElementRole.ACCENTBAR, x, top, col_w, 5, fill=accent,
                radius=b.rules.cardRadius, z=6)
        pad = 20.0
        title = col.title if col else ""
        title_h = b.line_px(b.typo.subtitleSize) + 12
        if title:
            b.text(ElementRole.CARD_TITLE, x + pad, top + pad, col_w - 2 * pad, title_h,
                   title, size_pt=b.typo.subtitleSize, color=b.tk.text, bold=True,
                   kind="heading", min_pt=b.typo.minBodySize, z=11)
        body_top = top + pad + (title_h + 8 if title else 0)
        bullets = col.bullets if col else []
        if bullets:
            _bullet_list(b, [s for s in bullets if s], x + pad, body_top,
                         col_w - 2 * pad, col_h - (body_top - top) - pad, accent)
        elif col and col.body:
            b.text(ElementRole.BODY, x + pad, body_top, col_w - 2 * pad,
                   col_h - (body_top - top) - pad, col.body,
                   size_pt=b.typo.bodySize, color=b.tk.textMuted, z=11)


def _timeline(b: LayoutBuilder) -> None:
    items = [i for i in b.content.items if (i.title or i.body or i.label)][:5]
    top = b.header(b.content.title or "")
    n = max(1, len(items))
    avail_h = b.cy + b.ch - top
    line_y = top + avail_h * 0.5
    b.shape(ElementRole.DECORATION, b.cx, line_y - 1.5, b.cw, 3, fill=b.tk.border,
            shape_type=ShapeType.RECT, z=4)
    seg = b.cw / n
    accents = b.tk.chart or [b.tk.accent]
    for i, it in enumerate(items):
        cx = b.cx + seg * i + seg / 2
        b.shape(ElementRole.MILESTONE, cx - 9, line_y - 9, 18, 18, fill=accents[i % len(accents)],
                shape_type=ShapeType.ELLIPSE, z=8)
        above = i % 2 == 0
        box_h = avail_h * 0.42
        box_y = line_y - 24 - box_h if above else line_y + 24
        b.text(ElementRole.MILESTONE, cx - seg / 2 + 8, box_y, seg - 16, box_h,
               f"{it.label}\n{it.title}".strip(), size_pt=b.typo.bodySize,
               color=b.tk.text, bold=True, align=Align.CENTER,
               valign=VAlign.BOTTOM if above else VAlign.TOP, min_pt=b.typo.minBodySize, z=11)


def _process(b: LayoutBuilder) -> None:
    items = [i for i in b.content.items if (i.title or i.body)][:5]
    top = b.header(b.content.title or "")
    n = max(1, len(items))
    gap = 14.0
    avail_h = b.cy + b.ch - top
    step_h = min(avail_h, 300.0)
    y = top + (avail_h - step_h) / 2
    step_w = (b.cw - gap * (n - 1)) / n
    accents = b.tk.chart or [b.tk.accent]
    for i, it in enumerate(items):
        x = b.cx + i * (step_w + gap)
        accent = accents[i % len(accents)]
        b.shape(ElementRole.STEP, x, y, step_w, step_h, fill=b.tk.surfaceElevated,
                stroke=b.tk.borderSubtle, stroke_w=1, radius=b.rules.cardRadius,
                shadow=b.rules.shadowIntensity, z=5)
        b.shape(ElementRole.BADGE, x + step_w / 2 - 20, y + 18, 40, 40, fill=accent,
                radius=20, z=7)
        b.text(ElementRole.BADGE, x + step_w / 2 - 20, y + 18, 40, 40, str(i + 1),
               size_pt=18, color=b.tk.textInverse, bold=True, align=Align.CENTER,
               valign=VAlign.MIDDLE, autofit=False, z=9)
        title_h = b.line_px(b.typo.subtitleSize) + 10
        b.text(ElementRole.CARD_TITLE, x + 12, y + 70, step_w - 24, title_h, it.title,
               size_pt=b.typo.subtitleSize, color=b.tk.text, bold=True, align=Align.CENTER,
               kind="heading", min_pt=14, z=8)
        if it.body:
            body_y = y + 70 + title_h + 6
            b.text(ElementRole.CARD_BODY, x + 12, body_y, step_w - 24, y + step_h - 12 - body_y,
                   it.body, size_pt=b.typo.captionSize + 1, color=b.tk.textMuted,
                   align=Align.CENTER, z=8)


def _architecture(b: LayoutBuilder) -> None:
    top = b.header(b.content.title or "系统架构")
    diagram = b.content.diagram
    legend = diagram.legend if diagram else []
    has_legend = bool(legend)
    diag_w = b.cw * (0.72 if has_legend else 1.0)
    diag_x = b.cx
    diag_y = top
    diag_h = b.cy + b.ch - top
    nodes = (diagram.nodes if diagram else []) or []
    if not nodes:
        # Fall back to bullets-as-boxes so the slide is never empty.
        nodes = [type("N", (), {"id": str(i), "label": s, "group": ""})()
                 for i, s in enumerate(b.content.bullets[:6])]
    accents = b.tk.chart or [b.tk.accent]
    cols = 2 if len(nodes) > 3 else 1
    rows = (len(nodes) + cols - 1) // cols
    gap = 18.0
    bw = (diag_w - gap * (cols - 1)) / max(1, cols)
    bh = min(90.0, (diag_h - gap * (rows - 1)) / max(1, rows))
    groups: dict[str, str] = {}
    for i, nd in enumerate(nodes):
        col = i % cols
        row = i // cols
        x = diag_x + col * (bw + gap)
        y = diag_y + row * (bh + gap)
        grp = getattr(nd, "group", "") or ""
        if grp not in groups:
            groups[grp] = accents[len(groups) % len(accents)]
        accent = groups[grp]
        b.shape(ElementRole.DIAGRAM, x, y, bw, bh, fill=b.tk.surfaceElevated,
                stroke=accent, stroke_w=2, radius=b.rules.cardRadius, z=6)
        b.text(ElementRole.DIAGRAM, x + 8, y, bw - 16, bh, getattr(nd, "label", ""),
               size_pt=b.typo.bodySize, color=b.tk.text, bold=True, align=Align.CENTER,
               valign=VAlign.MIDDLE, min_pt=12, z=8)
    if has_legend:
        lx = b.cx + diag_w + 18
        lw = b.cw - diag_w - 18
        b.shape(ElementRole.LEGEND, lx, top, lw, diag_h, fill=b.tk.surface,
                stroke=b.tk.borderSubtle, stroke_w=1, radius=b.rules.cardRadius, z=4)
        b.text(ElementRole.LEGEND, lx + 14, top + 12, lw - 28, diag_h - 24,
               "\n".join(f"• {s}" for s in legend), size_pt=b.typo.captionSize + 1,
               color=b.tk.textMuted, valign=VAlign.TOP, z=8)


def _data_chart(b: LayoutBuilder) -> None:
    top = b.header(b.content.title or "数据分析")
    chart = b.content.chart or ChartContent()
    has_insight = bool(chart.insight or b.content.body)
    chart_w = b.cw * (0.66 if has_insight else 1.0)
    chart_h = b.cy + b.ch - top
    b.shape(ElementRole.CHART, b.cx, top, chart_w, chart_h, fill=b.tk.surface,
            stroke=b.tk.borderSubtle, stroke_w=1, radius=b.rules.cardRadius, z=4)
    chart_el = SlideElement(
        element_id=b._id("chart"), role=ElementRole.CHART, type=ElementType.CHART,
        bbox=BBox(x=b.cx + 10, y=top + 10, width=chart_w - 20, height=chart_h - 20),
        z_index=6, chart=chart,
    )
    b.elements.append(chart_el)
    if has_insight:
        ix = b.cx + chart_w + 18
        iw = b.cw - chart_w - 18
        b.shape(ElementRole.BODY, ix, top, iw, chart_h, fill=b.tk.surfaceElevated,
                stroke=b.tk.borderSubtle, stroke_w=1, radius=b.rules.cardRadius, z=4)
        b.shape(ElementRole.ACCENTBAR, ix, top, iw, 5, fill=b.tk.accent,
                radius=b.rules.cardRadius, z=6)
        b.text(ElementRole.BODY, ix + 16, top + 18, iw - 32, chart_h - 36,
               chart.insight or b.content.body, size_pt=b.typo.bodySize,
               color=b.tk.text, valign=VAlign.TOP, z=8)


def _quote_center(b: LayoutBuilder) -> None:
    q = b.content.quote
    text = (q.text if q else "") or b.content.body
    author = (q.author if q else "") or b.content.meta
    b.text(ElementRole.QUOTE, b.cx + b.cw * 0.08, b.cy + b.ch * 0.22, b.cw * 0.84,
           b.ch * 0.46, f"“{text}”", size_pt=36, color=b.tk.text, bold=True,
           align=Align.CENTER, valign=VAlign.MIDDLE, kind="heading", min_pt=22, z=11)
    if author:
        b.text(ElementRole.META, b.cx, b.cy + b.ch * 0.74, b.cw, 50, f"— {author}",
               size_pt=b.typo.subtitleSize, color=b.tk.accent, align=Align.CENTER,
               valign=VAlign.MIDDLE, z=11)


def _code_block(b: LayoutBuilder) -> None:
    top = b.header(b.content.title or "Code")
    code = b.content.code
    ann = (code.annotation if code else "") or b.content.body
    has_ann = bool(ann)
    code_h = (b.cy + b.ch - top) * (0.72 if has_ann else 1.0)
    b.shape(ElementRole.CODE, b.cx, top, b.cw, code_h, fill=b.tk.surfaceElevated,
            stroke=b.tk.border, stroke_w=1, radius=8, z=4)
    src = code.code if code else ""
    b.text(ElementRole.CODE, b.cx + 16, top + 14, b.cw - 32, code_h - 28, src,
           size_pt=b.typo.bodySize, color=b.tk.text, align=Align.LEFT, valign=VAlign.TOP,
           kind="code", min_pt=11, line_height=1.4, z=8)
    if has_ann:
        b.text(ElementRole.BODY, b.cx, top + code_h + 12, b.cw,
               (b.cy + b.ch) - (top + code_h + 12), ann, size_pt=b.typo.bodySize,
               color=b.tk.textMuted, z=8)


def _summary_bullets(b: LayoutBuilder) -> None:
    bullets = [s for s in b.content.bullets if (s or "").strip()][:7]
    if not bullets and b.content.body:
        bullets = [s for s in b.content.body.split("\n") if s.strip()][:7]
    footer = b.content.footer
    top = b.header(b.content.title or "总结")
    foot_h = 64.0 if footer else 0.0
    list_h = (b.cy + b.ch - top) - foot_h - (12 if footer else 0)
    _bullet_list(b, bullets, b.cx, top, b.cw, list_h, b.tk.accent, big=True)
    if footer:
        fy = b.cy + b.ch - foot_h
        b.shape(ElementRole.FOOTER, b.cx, fy, b.cw, foot_h, fill=b.tk.primary,
                radius=b.rules.cardRadius, z=5)
        b.text(ElementRole.FOOTER, b.cx + 18, fy, b.cw - 36, foot_h, footer,
               size_pt=b.typo.subtitleSize, color=b.tk.textInverse, bold=True,
               align=Align.CENTER, valign=VAlign.MIDDLE, z=8)


# ---------------------------------------------------------------------------
def _bullet_list(b: LayoutBuilder, bullets, x, y, w, h, accent, *, big=False):
    bullets = [s for s in bullets if (s or "").strip()]
    n = max(1, len(bullets))
    row_h = min((h / n), 86.0 if big else 64.0)
    size = b.typo.bodySize + (3 if big else 0)
    for i, item in enumerate(bullets):
        ry = y + i * row_h
        dot = 9.0 if big else 7.0
        b.shape(ElementRole.DECORATION, x + 2, ry + row_h / 2 - dot / 2, dot, dot,
                fill=accent, shape_type=ShapeType.ELLIPSE, z=7)
        b.text(ElementRole.BULLET, x + 22, ry, w - 28, row_h, item, size_pt=size,
               color=b.tk.text, valign=VAlign.MIDDLE, min_pt=b.typo.minBodySize, z=8)


RENDERERS: dict[str, Callable[[LayoutBuilder], None]] = {
    "cover-center": _cover_center,
    "toc-simple": _toc_simple,
    "chapter-break": _chapter_break,
    "three-cards": _three_cards,
    "left-right": _left_right,
    "timeline": _timeline,
    "process": _process,
    "architecture": _architecture,
    "data-chart": _data_chart,
    "quote-center": _quote_center,
    "code-block": _code_block,
    "summary-bullets": _summary_bullets,
}


def render_layout(layout_id: str, theme: Theme, content: SlideContent,
                  canvas: Canvas) -> tuple[list[SlideElement], SlideBackground]:
    """Build the positioned elements + background for one slide."""
    renderer = RENDERERS.get(layout_id)
    builder = LayoutBuilder(theme, content, canvas)
    if renderer is None:
        # Unknown layout: degrade to summary bullets so we never crash.
        renderer = _summary_bullets
    renderer(builder)
    return builder.elements, builder.background()
