"""PreviewRenderer — SlideIR -> per-page PNG via Pillow.

We render previews from the *same* SlideIR the .pptx is built from, so the
preview is a faithful proxy for the file (and for what the Validator checked).
This avoids a LibreOffice/headless-Office dependency entirely.

A ``PreviewProvider`` interface is exposed so a higher-fidelity provider
(LibreOffice, headless renderer) can be slotted in later without touching
callers.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageDraw, ImageFont

from .schema import (
    PX_PER_PT,
    Align,
    ChartContent,
    SlideElement,
    SlideIR,
    ThemeTokens,
    VAlign,
)
from .text_metrics import TEXT_INSET_X, TEXT_INSET_Y, _is_wide

# Font resolution -----------------------------------------------------------
_SANS_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyh.ttf",
    r"C:\Windows\Fonts\msyhl.ttc", r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\Deng.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]
_SANS_BOLD_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\simhei.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
]
_MONO_CANDIDATES = [
    r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\cour.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]


def _first_existing(paths: list[str]) -> str | None:
    for p in paths:
        if os.path.exists(p):
            return p
    return None


_RESOLVED = {
    "sans": _first_existing(_SANS_CANDIDATES),
    "sans_bold": _first_existing(_SANS_BOLD_CANDIDATES) or _first_existing(_SANS_CANDIDATES),
    "mono": _first_existing(_MONO_CANDIDATES),
}
_FONT_CACHE: dict[tuple[str, int, bool], ImageFont.FreeTypeFont] = {}


def _font(kind: str, size_px: int, bold: bool) -> ImageFont.FreeTypeFont:
    size_px = max(6, int(round(size_px)))
    key = (kind, size_px, bold)
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    if kind == "code":
        path = _RESOLVED["mono"] or _RESOLVED["sans"]
    else:
        path = _RESOLVED["sans_bold"] if bold else _RESOLVED["sans"]
    try:
        font = ImageFont.truetype(path, size_px) if path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def fonts_available() -> bool:
    return bool(_RESOLVED["sans"])


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: float) -> list[str]:
    out: list[str] = []
    for para in text.split("\n"):
        if para == "":
            out.append("")
            continue
        line = ""
        i = 0
        tokens: list[str] = []
        buf = ""
        for ch in para:
            if _is_wide(ch) or ch in "，。！？；：、（）【】《》":
                if buf:
                    tokens.append(buf); buf = ""
                tokens.append(ch)
            elif ch == " ":
                buf += ch; tokens.append(buf); buf = ""
            else:
                buf += ch
        if buf:
            tokens.append(buf)
        for tok in tokens:
            trial = line + tok
            if draw.textlength(trial, font=font) > max_w and line:
                out.append(line.rstrip())
                line = tok if tok.strip() else ""
            else:
                line = trial
        out.append(line.rstrip())
    return out


class PreviewProvider(Protocol):
    def render_slide(self, ir: SlideIR, tokens: ThemeTokens, scale: float) -> Image.Image: ...


class PillowPreviewProvider:
    """Default provider: deterministic SlideIR -> PNG, no external office."""

    def render_slide(self, ir: SlideIR, tokens: ThemeTokens, scale: float = 1.0) -> Image.Image:
        W = int(ir.canvas.width * scale)
        H = int(ir.canvas.height * scale)
        img = Image.new("RGB", (W, H), _hex(ir.background.color))
        draw = ImageDraw.Draw(img)
        for el in sorted(ir.elements, key=lambda e: e.z_index):
            self._draw(draw, el, tokens, scale)
        return img

    def _draw(self, draw, el: SlideElement, tokens: ThemeTokens, scale: float) -> None:
        t = el.type.value
        if t == "group":
            for c in sorted(el.children, key=lambda e: e.z_index):
                self._draw(draw, c, tokens, scale)
            return
        b = el.bbox
        x0, y0 = b.x * scale, b.y * scale
        x1, y1 = b.x2 * scale, b.y2 * scale
        if t in ("shape", "line"):
            st = el.shape_style
            fill = _hex(st.fill) if st and st.fill else None
            outline = _hex(st.stroke) if st and st.stroke and st.strokeWidth else None
            width = int(round((st.strokeWidth if st else 0) * scale)) or 1
            if el.shape_type and el.shape_type.value == "ellipse":
                draw.ellipse([x0, y0, x1, y1], fill=fill, outline=outline, width=width)
            else:
                radius = (st.radius if st else 0) * scale
                if radius > 0:
                    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill,
                                           outline=outline, width=width)
                else:
                    draw.rectangle([x0, y0, x1, y1], fill=fill, outline=outline, width=width)
            if el.text:
                self._draw_text(draw, el, tokens, scale)
        elif t == "text":
            self._draw_text(draw, el, tokens, scale)
        elif t == "chart":
            self._draw_chart(draw, el, tokens, scale)

    def _draw_text(self, draw, el: SlideElement, tokens: ThemeTokens, scale: float) -> None:
        ts = el.text_style
        if not ts or not (el.text or "").strip():
            return
        b = el.bbox
        size_px = int(round(ts.fontSize * PX_PER_PT * scale))
        kind = ts.role if ts.role in ("heading", "body", "code") else "body"
        # The mono font lacks CJK glyphs; for code containing CJK, fall back to
        # the CJK sans so the preview shows real characters, not tofu boxes.
        if kind == "code" and any(_is_wide(c) for c in el.text):
            kind = "body"
        font = _font(kind, size_px, ts.bold)
        inner_x = (b.x + TEXT_INSET_X) * scale
        inner_w = (b.width - 2 * TEXT_INSET_X) * scale
        inner_y = (b.y + TEXT_INSET_Y) * scale
        inner_h = (b.height - 2 * TEXT_INSET_Y) * scale
        lines = _wrap(draw, el.text, font, inner_w)
        line_h = size_px * ts.lineHeight
        block_h = size_px * 1.16 + max(0, len(lines) - 1) * line_h
        if ts.valign == VAlign.MIDDLE:
            cy = inner_y + max(0, (inner_h - block_h) / 2)
        elif ts.valign == VAlign.BOTTOM:
            cy = inner_y + max(0, inner_h - block_h)
        else:
            cy = inner_y
        color = _hex(ts.color)
        for line in lines:
            lw = draw.textlength(line, font=font)
            if ts.align == Align.CENTER:
                lx = inner_x + (inner_w - lw) / 2
            elif ts.align == Align.RIGHT:
                lx = inner_x + (inner_w - lw)
            else:
                lx = inner_x
            draw.text((lx, cy), line, font=font, fill=color)
            cy += line_h

    def _draw_chart(self, draw, el: SlideElement, tokens: ThemeTokens, scale: float) -> None:
        chart: ChartContent = el.chart or ChartContent()
        b = el.bbox
        x0, y0 = b.x * scale, b.y * scale
        w, h = b.width * scale, b.height * scale
        pad = 16 * scale
        plot_x0 = x0 + pad * 2.2
        plot_y0 = y0 + pad
        plot_x1 = x0 + w - pad
        plot_y1 = y0 + h - pad * 2.2
        palette = [_hex(c) for c in (tokens.chart or [tokens.accent])]
        axis = _hex(tokens.textMuted)
        draw.line([plot_x0, plot_y0, plot_x0, plot_y1], fill=axis, width=max(1, int(scale)))
        draw.line([plot_x0, plot_y1, plot_x1, plot_y1], fill=axis, width=max(1, int(scale)))
        cats = chart.categories or []
        series = chart.series or []
        if not cats or not series:
            return
        max_v = max((max(s.values) for s in series if s.values), default=1.0) or 1.0
        n_cat = len(cats)
        n_ser = len(series)
        group_w = (plot_x1 - plot_x0) / max(1, n_cat)
        if chart.type in ("line", "area"):
            for si, s in enumerate(series):
                pts = []
                for ci, v in enumerate(s.values[:n_cat]):
                    px = plot_x0 + group_w * (ci + 0.5)
                    py = plot_y1 - (v / max_v) * (plot_y1 - plot_y0)
                    pts.append((px, py))
                if len(pts) > 1:
                    draw.line(pts, fill=palette[si % len(palette)], width=max(2, int(2 * scale)))
        else:  # column / bar / pie -> draw as columns for the thumbnail
            bar_w = group_w / (n_ser + 1)
            font = _font("body", int(10 * scale), False)
            for ci in range(n_cat):
                for si, s in enumerate(series):
                    if ci >= len(s.values):
                        continue
                    v = s.values[ci]
                    bx0 = plot_x0 + group_w * ci + bar_w * (si + 0.5)
                    bh = (v / max_v) * (plot_y1 - plot_y0)
                    draw.rectangle([bx0, plot_y1 - bh, bx0 + bar_w, plot_y1],
                                   fill=palette[si % len(palette)])
                label = str(cats[ci])
                lw = draw.textlength(label, font=font)
                draw.text((plot_x0 + group_w * ci + (group_w - lw) / 2, plot_y1 + 4 * scale),
                          label, font=font, fill=axis)


def _hex(color: str | None, fallback: str = "#000000") -> tuple[int, int, int]:
    h = (color or fallback).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        h = fallback.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


_provider = PillowPreviewProvider()


def render_previews(slides: list[SlideIR], tokens: ThemeTokens, out_dir: str | Path,
                    *, scale: float = 1.0, prefix: str = "slide") -> list[str]:
    """Render each slide to ``out_dir/<prefix>-NN.png``; return relative file names."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for ir in slides:
        img = _provider.render_slide(ir, tokens, scale)
        name = f"{prefix}-{ir.slide_index:02d}.png"
        img.save(str(out / name), "PNG")
        names.append(name)
    return names
