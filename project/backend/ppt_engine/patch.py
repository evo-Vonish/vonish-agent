"""Apply an :class:`ElementPatch` to a :class:`SlideIR` (Phase-2 element edits).

The Phase-2 protocol lets the agent (or the workbench) make surgical,
element-level edits without regenerating a slide from scratch: change a single
run of text, nudge a box, recolour a shape, delete a decoration. Each
:class:`PatchOperation` targets one element by ``element_id`` and mutates only
that element. Patches are applied to a *copy* of the IR — the input is never
touched — so callers can diff / roll back.

``apply_patch_and_rerender`` is the convenience path: apply, then re-render the
whole deck .pptx and just the patched slide's preview PNG.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .preview import render_previews
from .renderer import render_pptx
from .schema import (
    Align,
    ElementPatch,
    PatchOperation,
    ShapeStyle,
    SlideElement,
    SlideIR,
    TextStyle,
    Theme,
    ThemeTokens,
    VAlign,
)


# -- element lookup ---------------------------------------------------------
def _find_element(ir: SlideIR, element_id: str) -> Optional[SlideElement]:
    for el in ir.all_elements():
        if el.element_id == element_id:
            return el
    return None


def _remove_element(ir: SlideIR, element_id: str) -> bool:
    """Remove an element from the top-level list or from its parent's children."""
    for i, el in enumerate(ir.elements):
        if el.element_id == element_id:
            ir.elements.pop(i)
            return True
    for parent in ir.all_elements():
        for i, child in enumerate(parent.children):
            if child.element_id == element_id:
                parent.children.pop(i)
                return True
    return False


# -- coercion helpers -------------------------------------------------------
def _coerce_align(value: Any) -> Optional[Align]:
    try:
        return value if isinstance(value, Align) else Align(str(value).lower())
    except Exception:
        return None


def _coerce_valign(value: Any) -> Optional[VAlign]:
    try:
        return value if isinstance(value, VAlign) else VAlign(str(value).lower())
    except Exception:
        return None


def _coerce_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# -- per-op application -----------------------------------------------------
def _apply_replace_text(el: SlideElement, op: PatchOperation) -> None:
    if op.value is not None:
        el.text = op.value


def _apply_update_style(el: SlideElement, op: PatchOperation) -> None:
    ts = el.text_style or TextStyle()
    ch = op.changes or {}
    if "fontSize" in ch:
        fs = _coerce_float(ch["fontSize"])
        if fs is not None:
            ts.fontSize = fs
    if "color" in ch and ch["color"]:
        ts.color = str(ch["color"])
    if "bold" in ch:
        ts.bold = bool(ch["bold"])
    if "italic" in ch:
        ts.italic = bool(ch["italic"])
    if "fontFamily" in ch and ch["fontFamily"]:
        ts.fontFamily = str(ch["fontFamily"])
    if "align" in ch:
        align = _coerce_align(ch["align"])
        if align is not None:
            ts.align = align
    if "valign" in ch:
        valign = _coerce_valign(ch["valign"])
        if valign is not None:
            ts.valign = valign
    el.text_style = ts


def _apply_update_shape_style(el: SlideElement, op: PatchOperation) -> None:
    ss = el.shape_style or ShapeStyle()
    ch = op.changes or {}
    if "fill" in ch:
        ss.fill = str(ch["fill"]) if ch["fill"] else None
    if "stroke" in ch:
        ss.stroke = str(ch["stroke"]) if ch["stroke"] else None
    if "strokeWidth" in ch:
        sw = _coerce_float(ch["strokeWidth"])
        if sw is not None:
            ss.strokeWidth = sw
    if "radius" in ch:
        r = _coerce_float(ch["radius"])
        if r is not None:
            ss.radius = r
    el.shape_style = ss


def _apply_move(el: SlideElement, op: PatchOperation) -> None:
    ch = op.changes or {}
    if "x" in ch:
        x = _coerce_float(ch["x"])
        if x is not None:
            el.bbox.x = x
    if "y" in ch:
        y = _coerce_float(ch["y"])
        if y is not None:
            el.bbox.y = y


def _apply_resize(el: SlideElement, op: PatchOperation) -> None:
    ch = op.changes or {}
    if "width" in ch:
        w = _coerce_float(ch["width"])
        if w is not None:
            el.bbox.width = w
    if "height" in ch:
        h = _coerce_float(ch["height"])
        if h is not None:
            el.bbox.height = h


def _apply_add_decoration(el: SlideElement, op: PatchOperation) -> None:
    # No-op record: decoration metadata is acknowledged but not materialised
    # here (a later pass / renderer owns decoration synthesis).
    return None


def apply_patch(slide_ir: SlideIR, patch: ElementPatch) -> SlideIR:
    """Return a new :class:`SlideIR` with ``patch`` applied to a deep copy.

    Each operation locates its element by ``element_id`` (``op.target``) and
    mutates only that element. Unknown ids or unknown ops are skipped safely.
    With ``patch_scope == "element_only"`` no other element is ever moved.
    """
    new_ir = slide_ir.model_copy(deep=True)

    for op in patch.operations:
        try:
            if op.op == "delete":
                _remove_element(new_ir, op.target)
                continue
            el = _find_element(new_ir, op.target)
            if el is None:
                continue
            if op.op == "replace_text":
                _apply_replace_text(el, op)
            elif op.op == "update_style":
                _apply_update_style(el, op)
            elif op.op == "update_shape_style":
                _apply_update_shape_style(el, op)
            elif op.op == "move":
                _apply_move(el, op)
            elif op.op == "resize":
                _apply_resize(el, op)
            elif op.op == "add_decoration":
                _apply_add_decoration(el, op)
            # unknown op -> skip
        except Exception:
            # A single bad op must never corrupt the rest of the patch.
            continue

    return new_ir


def apply_patch_and_rerender(
    slides: list[SlideIR],
    patch: ElementPatch,
    theme: Theme,
    out_pptx: str,
    out_preview_dir: str,
    tokens: Optional[ThemeTokens] = None,
) -> dict:
    """Apply ``patch`` to the matching slide, then re-render deck + one preview.

    The slide is matched by ``patch.slide_index``. The whole deck .pptx is
    re-rendered (so the file stays a single coherent artifact) but only the
    patched slide's preview PNG is regenerated. Returns
    ``{"success": True, "slide_index": i, "pptx": out_pptx}`` or, on failure,
    ``{"success": False, "error": str}``.
    """
    try:
        idx = patch.slide_index
        target_pos = next(
            (i for i, ir in enumerate(slides) if ir.slide_index == idx), None)
        if target_pos is None and 0 <= idx < len(slides):
            target_pos = idx
        if target_pos is None:
            return {"success": False, "error": f"slide_index {idx} not found"}

        patched = apply_patch(slides[target_pos], patch)
        new_slides = list(slides)
        new_slides[target_pos] = patched

        resolved_tokens = tokens if tokens is not None else theme.tokens

        render_pptx(new_slides, out_pptx, resolved_tokens)
        Path(out_preview_dir).mkdir(parents=True, exist_ok=True)
        render_previews([patched], resolved_tokens, out_preview_dir)

        return {"success": True, "slide_index": patched.slide_index, "pptx": out_pptx}
    except Exception as exc:
        return {"success": False, "error": f"rerender failed: {exc}"}
