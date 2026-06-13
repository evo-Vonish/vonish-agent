"""Engine orchestrator — the one entry point for producing/patching a deck.

    DeckDesignSpec
      -> SlideIR            (layout engine)
      -> repair loop        (validate + auto-fix, <=3 rounds)
      -> PPTX               (renderer)
      -> PNG previews       (Pillow)
      -> ValidationReport + manifest written to the workspace

``generate_deck`` builds a deck from a spec. ``apply_deck_patch`` loads the
persisted SlideIR for an existing deck, applies an element-level patch, and
re-renders/re-validates in place. Both share ``_finalize_deck`` so a patched
deck goes through the exact same quality gate as a fresh one. Nothing here
decides colour/geometry — that is all upstream.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .autorepair import repair_loop
from .ir import build_deck_ir
from .patch import apply_patch
from .preview import render_previews
from .registry import get_theme_registry
from .renderer import render_pptx
from .schema import (
    ArtifactPreview,
    DeckDesignSpec,
    DeckResult,
    ElementBox,
    ElementPatch,
    IssueType,
    PatchOperation,
    Severity,
    SlideIR,
    SlideMeta,
    SuggestedFix,
    Theme,
    ValidatorIssue,
    VisualFinding,
)
from .versions import list_versions, load_version_slides, snapshot_version

# image-grounded issue types that block delivery
_VISUAL_BLOCKING = {IssueType.RENDERED_BLANK, IssueType.RENDER_TEXT_MISSING}


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


def _finalize_deck(
    deck_id: str,
    title: str,
    theme: Theme,
    slides: list[SlideIR],
    workspace_root: Path,
    out_dir: Path,
    log: list[str],
    *,
    spec: DeckDesignSpec | None = None,
    existing_deckspec_rel: str = "",
    scale: float = 1.0,
    max_repair_rounds: int = 3,
    visual_qa: bool = False,
    version_kind: str = "generate",
    version_label: str = "",
) -> DeckResult:
    """Validate + repair + render + preview + persist. Shared by generate/patch."""
    # 1. validate + auto-repair (mutates SlideIR in place)
    report, rounds = repair_loop(slides, theme, max_rounds=max_repair_rounds)
    report.deck_id = deck_id
    report.validation_id = f"val-{deck_id}"
    report.timestamp = _now_iso()
    log.append(f"repair rounds={rounds}, grade={report.delivery_grade}, "
               f"errors={report.summary.error_count}, warnings={report.summary.warning_count}")

    # 2. render PPTX from the repaired IR
    out_dir.mkdir(parents=True, exist_ok=True)
    pptx_path = out_dir / "deck.pptx"
    render_pptx(slides, pptx_path, theme.tokens)
    log.append(f"rendered {pptx_path.name}")

    # 3. preview PNGs
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

    # 4. MISSING_PREVIEW check (never deliver a deck with a missing render)
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

    # 4b. optional L2 visual QA on the rendered pixels
    visual_findings: list[VisualFinding] = []
    if visual_qa:
        from .visual_qa import run_visual_qa
        png_abs = [str(workspace_root / p.path) for p in previews]
        visual_findings, vissues = run_visual_qa(slides, png_abs, theme)
        for vi in vissues:
            report.issues.append(vi)
            report.summary.total_issues += 1
            if vi.severity == Severity.ERROR:
                report.summary.error_count += 1
                if vi.type in _VISUAL_BLOCKING:
                    report.deliverable = False
                    if vi.type.value not in report.blocking_issue_types:
                        report.blocking_issue_types.append(vi.type.value)
            elif vi.severity == Severity.WARNING:
                report.summary.warning_count += 1
        if report.summary.error_count > 0:
            report.delivery_grade = "blocked" if not report.deliverable else "acceptable"
        log.append(f"visual QA: {len(vissues)} image issue(s)")

    # 5. slide meta for the workbench overlay
    slides_meta = [SlideMeta(slide_id=ir.slide_id, slide_index=ir.slide_index,
                             layout_id=ir.layout_id, title=_slide_title(ir),
                             preview=prev.path, elements=_element_boxes(ir))
                   for ir, prev in zip(slides, previews)]

    # 6. persist spec / IR / manifest sidecars
    deckspec_path = out_dir / "deck.deckspec.json"
    slideir_path = out_dir / "deck.slideir.json"
    manifest_path = out_dir / "deck.manifest.json"
    if spec is not None:
        deckspec_path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
        deck_spec_rel = _rel(deckspec_path, workspace_root)
    else:
        deck_spec_rel = existing_deckspec_rel or _rel(deckspec_path, workspace_root)
    slideir_path.write_text(
        json.dumps([s.model_dump(mode="json") for s in slides], ensure_ascii=False, indent=2),
        encoding="utf-8")

    # snapshot this state for version history / rollback
    versions = snapshot_version(out_dir, slides, label=version_label or version_kind,
                                kind=version_kind, grade=report.delivery_grade)

    result = DeckResult(
        artifact_id=f"ppt-{deck_id}", deck_id=deck_id,
        title=title or (_slide_title(slides[0]) if slides else ""),
        theme_id=theme.theme_id,
        pptx_path=_rel(pptx_path, workspace_root),
        deck_spec_path=deck_spec_rel,
        slide_ir_path=_rel(slideir_path, workspace_root),
        manifest_path=_rel(manifest_path, workspace_root),
        slide_count=len(slides), previews=previews, slides_meta=slides_meta,
        validation=report, versions=versions, visual_findings=visual_findings,
        generation_log=log, created_at=_now_iso())
    manifest_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result


def generate_deck(
    spec: DeckDesignSpec,
    workspace_dir: str | Path,
    *,
    out_subdir: str = "outputs/ppt",
    scale: float = 1.0,
    max_repair_rounds: int = 3,
    visual_qa: bool = False,
    theme: Theme | None = None,
) -> DeckResult:
    workspace_root = Path(workspace_dir).resolve()
    deck_id = spec.deck_id or f"deck-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    spec.deck_id = deck_id
    spec.created_at = spec.created_at or _now_iso()
    theme = theme or get_theme_registry().get(spec.theme_id)

    log: list[str] = [f"theme={theme.theme_id}", f"slides={len(spec.slides)}"]
    slides = build_deck_ir(spec, theme)
    log.append(f"built SlideIR ({sum(len(s.all_elements()) for s in slides)} elements)")

    out_dir = workspace_root / out_subdir / deck_id
    title = spec.title or (_slide_title(slides[0]) if slides else "")
    return _finalize_deck(deck_id, title, theme, slides, workspace_root, out_dir, log,
                          spec=spec, scale=scale, max_repair_rounds=max_repair_rounds,
                          visual_qa=visual_qa, version_kind="generate", version_label="initial generate")


def _resolve_deck_dir(workspace_root: Path, deck_path: str) -> Path:
    """A deck path may point at deck.pptx, a sidecar json, or the deck dir."""
    p = (workspace_root / deck_path).resolve()
    if p.suffix:  # a file -> its containing deck dir
        return p.parent
    return p


def apply_deck_patch(
    workspace_dir: str | Path,
    deck_path: str,
    slide_index: int,
    operations: list[dict],
    *,
    reasoning: str = "",
    patch_scope: str = "element_only",
    visual_qa: bool = False,
    theme: Theme | None = None,
) -> DeckResult:
    """Apply an element-level patch to an existing deck and re-render in place.

    Loads the persisted ``deck.slideir.json``, applies the ``ElementPatch`` to
    the targeted slide, then runs the same finalize gate (validate + repair +
    render + preview + manifest) so the patched deck is held to the same bar.
    """
    workspace_root = Path(workspace_dir).resolve()
    deck_dir = _resolve_deck_dir(workspace_root, deck_path)
    slideir_path = deck_dir / "deck.slideir.json"
    manifest_path = deck_dir / "deck.manifest.json"
    if not slideir_path.exists():
        raise FileNotFoundError(f"SlideIR not found for deck at {deck_dir}")

    raw = json.loads(slideir_path.read_text(encoding="utf-8"))
    slides = [SlideIR.model_validate(d) for d in raw]
    if not slides:
        raise ValueError("deck has no slides")

    deck_id = slides[0].deck_id or deck_dir.name
    theme = theme or get_theme_registry().get(slides[0].theme_id)

    # preserve title / deckspec path from the existing manifest when available
    title = ""
    deck_spec_rel = ""
    if manifest_path.exists():
        try:
            prev = json.loads(manifest_path.read_text(encoding="utf-8"))
            title = prev.get("title", "")
            deck_spec_rel = prev.get("deck_spec_path", "")
        except Exception:
            pass

    pos = next((i for i, ir in enumerate(slides) if ir.slide_index == slide_index), None)
    if pos is None:
        if 0 <= slide_index < len(slides):
            pos = slide_index
        else:
            raise IndexError(f"slide_index {slide_index} out of range")

    ops = [PatchOperation.model_validate(o) for o in (operations or [])]
    patch = ElementPatch(deck_id=deck_id, slide_id=slides[pos].slide_id,
                         slide_index=slides[pos].slide_index, operations=ops,
                         patch_scope=patch_scope, reasoning=reasoning)
    slides[pos] = apply_patch(slides[pos], patch)

    log = [f"patch slide {slide_index}: {len(ops)} op(s)"]
    if reasoning:
        log.append(f"reason: {reasoning[:200]}")
    label = reasoning[:80] or f"patch slide {slide_index}"
    return _finalize_deck(deck_id, title, theme, slides, workspace_root, deck_dir, log,
                          spec=None, existing_deckspec_rel=deck_spec_rel,
                          visual_qa=visual_qa, version_kind="patch", version_label=label)


def list_deck_versions(workspace_dir: str | Path, deck_path: str) -> list[dict]:
    """List a deck's saved versions (newest last)."""
    workspace_root = Path(workspace_dir).resolve()
    deck_dir = _resolve_deck_dir(workspace_root, deck_path)
    return [v.model_dump(mode="json") for v in list_versions(deck_dir)]


def restore_deck_version(
    workspace_dir: str | Path,
    deck_path: str,
    version_id: str,
    *,
    visual_qa: bool = False,
    theme: Theme | None = None,
) -> DeckResult:
    """Roll a deck back to a saved snapshot and re-render in place.

    The restore itself is recorded as a new ``restore`` version, so history
    stays linear (you can always roll forward again).
    """
    workspace_root = Path(workspace_dir).resolve()
    deck_dir = _resolve_deck_dir(workspace_root, deck_path)
    slides = load_version_slides(deck_dir, version_id)
    if not slides:
        raise ValueError(f"version {version_id} has no slides")
    deck_id = slides[0].deck_id or deck_dir.name
    theme = theme or get_theme_registry().get(slides[0].theme_id)

    title = ""
    deck_spec_rel = ""
    manifest_path = deck_dir / "deck.manifest.json"
    if manifest_path.exists():
        try:
            prev = json.loads(manifest_path.read_text(encoding="utf-8"))
            title = prev.get("title", "")
            deck_spec_rel = prev.get("deck_spec_path", "")
        except Exception:
            pass

    log = [f"restore version {version_id}"]
    return _finalize_deck(deck_id, title, theme, slides, workspace_root, deck_dir, log,
                          spec=None, existing_deckspec_rel=deck_spec_rel,
                          visual_qa=visual_qa, version_kind="restore",
                          version_label=f"restored from {version_id}")
