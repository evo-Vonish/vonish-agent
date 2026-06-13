"""Engine orchestrator — the one entry point for producing a deck.

    DeckDesignSpec
      -> SlideIR            (layout engine)
      -> repair loop        (validate + auto-fix, <=3 rounds)
      -> PPTX               (renderer)
      -> PNG previews       (Pillow)
      -> ValidationReport + manifest written to the workspace

Returns a ``DeckResult`` with workspace-relative paths so the tool layer can
register the artifact and the frontend can open it. Nothing here decides
colour/geometry — that is all upstream.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .autorepair import repair_loop
from .ir import build_deck_ir
from .preview import render_previews
from .registry import get_theme_registry
from .renderer import render_pptx
from .schema import (
    ArtifactPreview,
    DeckDesignSpec,
    DeckResult,
    ElementBox,
    IssueType,
    Severity,
    SlideIR,
    SlideMeta,
    SuggestedFix,
    Theme,
    ValidatorIssue,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _slide_title(ir: SlideIR) -> str:
    for el in ir.elements:
        if el.role.value in ("title", "quote") and el.text.strip():
            return el.text.strip()[:80]
    for el in ir.all_elements():
        if el.type.value == "text" and el.text.strip():
            return el.text.strip()[:80]
    return f"Slide {ir.slide_index + 1}"


def _element_boxes(ir: SlideIR) -> list[ElementBox]:
    boxes: list[ElementBox] = []
    for el in ir.all_elements():
        if el.role.value in ("accent_bar", "decoration", "background"):
            continue
        boxes.append(ElementBox(element_id=el.element_id, role=el.role.value,
                                type=el.type.value, bbox=el.bbox.as_list(),
                                text=el.text[:300]))
    return boxes


def generate_deck(
    spec: DeckDesignSpec,
    workspace_dir: str | Path,
    *,
    out_subdir: str = "outputs/ppt",
    scale: float = 1.0,
    max_repair_rounds: int = 3,
    theme: Theme | None = None,
) -> DeckResult:
    workspace_root = Path(workspace_dir).resolve()
    deck_id = spec.deck_id or f"deck-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    spec.deck_id = deck_id
    spec.created_at = spec.created_at or _now_iso()
    theme = theme or get_theme_registry().get(spec.theme_id)

    log: list[str] = [f"theme={theme.theme_id}", f"slides={len(spec.slides)}"]

    # 1. layout -> SlideIR
    slides = build_deck_ir(spec, theme)
    log.append(f"built SlideIR ({sum(len(s.all_elements()) for s in slides)} elements)")

    # 2. validate + auto-repair (mutates SlideIR in place)
    report, rounds = repair_loop(slides, theme, max_rounds=max_repair_rounds)
    report.deck_id = deck_id
    report.validation_id = f"val-{deck_id}"
    report.timestamp = _now_iso()
    log.append(f"repair rounds={rounds}, grade={report.delivery_grade}, "
               f"errors={report.summary.error_count}, warnings={report.summary.warning_count}")

    # 3. render PPTX from the repaired IR
    out_dir = workspace_root / out_subdir / deck_id
    out_dir.mkdir(parents=True, exist_ok=True)
    pptx_path = out_dir / "deck.pptx"
    render_pptx(slides, pptx_path, theme.tokens)
    log.append(f"rendered {pptx_path.name}")

    # 4. preview PNGs
    previews_dir = out_dir / "previews"
    png_names = render_previews(slides, theme.tokens, previews_dir, scale=scale)
    previews: list[ArtifactPreview] = []
    for ir, name in zip(slides, png_names):
        png_path = previews_dir / name
        previews.append(ArtifactPreview(
            slide_id=ir.slide_id, slide_index=ir.slide_index,
            path=_rel(png_path, workspace_root),
            width=int(ir.canvas.width * scale), height=int(ir.canvas.height * scale),
            title=_slide_title(ir)))
    log.append(f"exported {len(previews)} previews")

    # 5. MISSING_PREVIEW check (never deliver a deck with a missing render)
    for ir, prev in zip(slides, previews):
        if not (workspace_root / prev.path).exists():
            report.issues.append(ValidatorIssue(
                id=f"iss-prev-{ir.slide_index}", type=IssueType.MISSING_PREVIEW,
                severity=Severity.ERROR, slide_id=ir.slide_id, slide_index=ir.slide_index,
                message="Preview image was not produced for this slide",
                fixable=False, suggested_fix=SuggestedFix(action="re_render")))
            report.summary.error_count += 1
            report.summary.total_issues += 1
            report.deliverable = False
            if "MISSING_PREVIEW" not in report.blocking_issue_types:
                report.blocking_issue_types.append("MISSING_PREVIEW")

    # 6. slide meta for the workbench overlay
    slides_meta = [SlideMeta(slide_id=ir.slide_id, slide_index=ir.slide_index,
                             layout_id=ir.layout_id, title=_slide_title(ir),
                             preview=prev.path, elements=_element_boxes(ir))
                   for ir, prev in zip(slides, previews)]

    # 7. persist spec / IR / manifest sidecars
    deckspec_path = out_dir / "deck.deckspec.json"
    slideir_path = out_dir / "deck.slideir.json"
    manifest_path = out_dir / "deck.manifest.json"
    deckspec_path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    slideir_path.write_text(
        json.dumps([s.model_dump(mode="json") for s in slides], ensure_ascii=False, indent=2),
        encoding="utf-8")

    result = DeckResult(
        artifact_id=f"ppt-{deck_id}", deck_id=deck_id, title=spec.title or _slide_title(slides[0]) if slides else spec.title,
        theme_id=theme.theme_id,
        pptx_path=_rel(pptx_path, workspace_root),
        deck_spec_path=_rel(deckspec_path, workspace_root),
        slide_ir_path=_rel(slideir_path, workspace_root),
        manifest_path=_rel(manifest_path, workspace_root),
        slide_count=len(slides), previews=previews, slides_meta=slides_meta,
        validation=report, generation_log=log, created_at=_now_iso())
    manifest_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result
