"""L3 design-judge framework — advisory, never blocks delivery.

This is the L3 layer from the design report: a PPTEval-style visual design
review on top of the L1 (rule) and L2 (image-grounded) gates. Where L1/L2
decide *deliverability*, L3 only offers *advice* — a 1-5 design score and
human-readable suggestions per slide. A bad L3 score never makes a deck
undeliverable.

Honest capability statement
---------------------------
There is **no** real multimodal LLM / VLM available in this environment (no
network, no API key, no local vision model installed). This module therefore
NEVER claims to have called a VLM. The shipped, working reviewer is the
``"mock"`` heuristic: a deterministic, seedless scorer derived purely from the
validator issues, L2 visual findings and slide element metadata that the engine
already produced. The other modes are honest about their limits:

    * ``disabled`` — no-op, returns ``enabled=False``.
    * ``mock``     — deterministic heuristic reviewer (provider ``mock-heuristic``).
    * ``local``    — would use a *local* vision model **iff** one were obviously
                     installed; since none is, it degrades gracefully to
                     ``disabled`` (it never raises and never fakes a call).
    * ``manual``   — emits a per-slide template (score 0) for a human reviewer.
    * ``auto``     — resolves to ``mock`` because there is no external VLM/API
                     key in the environment.

The concrete provider also implements the abstract
``VlmDesignJudge.judge(png_path, *, dimensions)`` interface from
``interfaces.py`` so downstream code can depend on the declared shape.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from .interfaces import VisualReview, VlmDesignJudge
from .schema import (
    DesignJudgeReport,
    DesignReview,
    Severity,
    ValidationReport,
    VisualFinding,
)

# ---------------------------------------------------------------------------
# modes
# ---------------------------------------------------------------------------
_MODES = ["disabled", "mock", "local", "manual", "auto"]


def get_judge_modes() -> list[str]:
    """All accepted ``mode`` strings for :func:`make_design_judge`."""
    return list(_MODES)


def _resolve_auto() -> str:
    """``auto`` resolves to a concrete mode.

    There is no external VLM endpoint or API key wired into this environment,
    so ``auto`` always resolves to the deterministic ``mock`` heuristic. This is
    intentional: we never silently pretend a real model is available. If a real
    provider were ever added, this is the single place that would learn to
    return ``"local"`` (or another concrete mode).
    """
    return "mock"


# ---------------------------------------------------------------------------
# issue-type -> human suggestion mapping (for the mock heuristic)
# ---------------------------------------------------------------------------
_ISSUE_SUGGESTIONS: dict[str, str] = {
    "TEXT_OVERFLOW": "Shorten the copy or let autofit shrink the font so text fits its box.",
    "ELEMENT_OVERLAP": "Separate overlapping elements; add spacing so nothing collides.",
    "OUT_OF_BOUNDS": "Pull the element back inside the canvas safe area.",
    "UNSAFE_MARGIN": "Respect the slide safe margins; keep content off the edges.",
    "TITLE_TOO_LONG": "Tighten the title to a short, scannable phrase.",
    "FONT_TOO_SMALL": "Increase the font size for legibility (raise above the minimum).",
    "COLOR_OUT_OF_THEME": "Replace the off-theme colour with a palette token.",
    "LOW_CONTRAST": "Increase text/background contrast for readability.",
    "FONT_CHAOS": "Consolidate to the theme's heading/body font families.",
    "EMPTY_SLIDE": "Add meaningful content; an empty slide reads as a mistake.",
    "OVERCROWDED_SLIDE": "Reduce the number of elements; split content across slides.",
    "MISSING_PREVIEW": "Re-render the slide; its preview image is missing.",
    "INCONSISTENT_STYLE": "Align styling with the rest of the deck for consistency.",
    "RENDERED_BLANK": "Slide renders near-blank — add content or fix the render.",
    "IMAGE_BLURRY": "Check raster assets; the slide looks low-sharpness.",
    "COLOR_DRIFT": "A prominent rendered colour drifts from the theme palette.",
    "RENDER_TEXT_MISSING": "Text did not render — check font availability or contrast.",
}

# L2 visual metrics that, when not ok, surface as a design note
_VISUAL_METRIC_NOTES: dict[str, str] = {
    "blankness": "Slide looks visually sparse / near-blank.",
    "sharpness": "Low edge sharpness — visuals may look soft or blurry.",
    "color_drift": "A dominant colour drifts from the theme palette.",
    "text_presence": "Some text may not be rendering visibly.",
}


# ---------------------------------------------------------------------------
# small input adapters — tolerate SlideMeta | dict, ValidationReport | dict
# ---------------------------------------------------------------------------
def _meta_field(meta: Any, name: str, default: Any = None) -> Any:
    if isinstance(meta, dict):
        return meta.get(name, default)
    return getattr(meta, name, default)


def _slide_key(meta: Any, fallback_index: int) -> tuple[str, int]:
    sid = _meta_field(meta, "slide_id", "") or ""
    sidx = _meta_field(meta, "slide_index", None)
    if sidx is None:
        sidx = fallback_index
    try:
        sidx = int(sidx)
    except (TypeError, ValueError):
        sidx = fallback_index
    if not sid:
        sid = f"slide-{sidx}"
    return str(sid), sidx


def _element_count(meta: Any) -> int:
    els = _meta_field(meta, "elements", []) or []
    try:
        return len(els)
    except TypeError:
        return 0


def _iter_issues(validation: ValidationReport | dict | None) -> list[dict[str, Any]]:
    """Normalise a ValidationReport / dict / None to a list of issue dicts."""
    if validation is None:
        return []
    issues: Iterable[Any]
    if isinstance(validation, ValidationReport):
        issues = validation.issues
    elif isinstance(validation, dict):
        issues = validation.get("issues", []) or []
    else:  # unknown shape — be defensive, never crash the caller
        issues = getattr(validation, "issues", []) or []

    out: list[dict[str, Any]] = []
    for it in issues:
        if isinstance(it, dict):
            itype = it.get("type", "")
            sev = it.get("severity", "")
            sidx = it.get("slide_index", 0)
            sid = it.get("slide_id", "")
            msg = it.get("message", "")
        else:
            itype = getattr(it, "type", "")
            sev = getattr(it, "severity", "")
            sidx = getattr(it, "slide_index", 0)
            sid = getattr(it, "slide_id", "")
            msg = getattr(it, "message", "")
        # enums -> their value
        itype = getattr(itype, "value", itype)
        sev = getattr(sev, "value", sev)
        try:
            sidx = int(sidx)
        except (TypeError, ValueError):
            sidx = 0
        out.append({
            "type": str(itype or ""),
            "severity": str(sev or ""),
            "slide_index": sidx,
            "slide_id": str(sid or ""),
            "message": str(msg or ""),
        })
    return out


def _iter_findings(
    findings: Iterable[VisualFinding | dict] | None,
) -> list[dict[str, Any]]:
    if not findings:
        return []
    out: list[dict[str, Any]] = []
    for f in findings:
        if isinstance(f, dict):
            out.append({
                "slide_index": int(f.get("slide_index", 0) or 0),
                "metric": str(f.get("metric", "") or ""),
                "ok": bool(f.get("ok", True)),
                "detail": str(f.get("detail", "") or ""),
            })
        else:
            out.append({
                "slide_index": int(getattr(f, "slide_index", 0) or 0),
                "metric": str(getattr(f, "metric", "") or ""),
                "ok": bool(getattr(f, "ok", True)),
                "detail": str(getattr(f, "detail", "") or ""),
            })
    return out


# ---------------------------------------------------------------------------
# the concrete provider
# ---------------------------------------------------------------------------
class VlmDesignJudgeProvider(VlmDesignJudge):
    """Concrete L3 design judge.

    Implements the abstract :meth:`judge` (single-image) interface AND a richer
    deck-level :meth:`judge_deck`. The ``mode`` selected at construction decides
    behaviour; the mock heuristic is the only mode that actually produces
    content, and it is fully deterministic (no seed, no randomness, no network).
    """

    #: which dimensions this judge reasons about (PPTEval-style)
    DIMENSIONS = ["aesthetics", "readability", "consistency", "hierarchy"]

    def __init__(self, mode: str = "auto") -> None:
        mode = (mode or "auto").lower().strip()
        if mode not in _MODES:
            mode = "auto"
        self.requested_mode = mode
        # resolve "auto" eagerly so callers can introspect what will run
        self.mode = _resolve_auto() if mode == "auto" else mode

    # -- VlmDesignJudge interface ------------------------------------------
    def judge(self, png_path: str, *, dimensions: list[str]) -> list[VisualReview]:
        """Single-image interface from ``interfaces.VlmDesignJudge``.

        We do NOT call a real VLM (none exists here). In ``mock`` mode we return
        a neutral, deterministic review per requested dimension so the declared
        interface is satisfied without ever faking a model call. In every other
        mode we return an empty list (no opinion).
        """
        dims = list(dimensions) if dimensions else list(self.DIMENSIONS)
        if self.mode != "mock":
            return []
        # No pixels are actually analysed here (that is the L2 layer's job);
        # this is an honest, content-free neutral baseline per dimension.
        return [
            VisualReview(
                score=4.0,
                dimension=dim,
                notes="mock-heuristic baseline (no VLM available); "
                      "see judge_deck for issue-grounded scoring",
            )
            for dim in dims
        ]

    # -- deck-level entry point --------------------------------------------
    def judge_deck(
        self,
        slides_meta: list,
        png_paths: list[str],
        validation: ValidationReport | dict | None = None,
        *,
        visual_findings: Iterable[VisualFinding | dict] | None = None,
        mode: Optional[str] = None,
    ) -> DesignJudgeReport:
        """Produce a :class:`DesignJudgeReport` for a whole deck.

        Advisory only — this is never consulted to gate delivery.

        Args:
            slides_meta: list of ``SlideMeta`` (or dicts) carrying
                ``slide_id`` / ``slide_index`` / ``elements``.
            png_paths: absolute preview PNG paths (positional, advisory; the
                mock heuristic does not read pixels — that is the L2 layer).
            validation: the deck ``ValidationReport`` (or dict / None).
            visual_findings: optional L2 ``VisualFinding`` list to fold in.
            mode: optional per-call override of the construction mode.
        """
        run_mode = self.mode
        if mode is not None:
            m = (mode or "auto").lower().strip()
            run_mode = _resolve_auto() if m == "auto" else m
            if run_mode not in _MODES:
                run_mode = "mock"

        slides_meta = list(slides_meta or [])

        try:
            if run_mode == "disabled":
                return self._report_disabled()
            if run_mode == "local":
                return self._report_local()
            if run_mode == "manual":
                return self._report_manual(slides_meta)
            # default / "mock"
            return self._report_mock(slides_meta, png_paths, validation, visual_findings)
        except Exception as exc:  # never crash the caller — advisory only
            return DesignJudgeReport(
                enabled=False, mode="disabled", provider="error",
                summary=f"design judge failed safely: {exc!r}")

    # -- mode implementations ----------------------------------------------
    def _report_disabled(self) -> DesignJudgeReport:
        return DesignJudgeReport(
            enabled=False, mode="disabled", provider="none",
            average_score=0.0, reviews=[],
            summary="L3 design judge disabled (no-op).")

    def _report_local(self) -> DesignJudgeReport:
        """Local vision model path — degrades gracefully when none installed.

        We only ever use a local model if one is *obviously* available. None is
        installed in this environment, so we degrade to ``disabled`` without
        raising and without faking a call.
        """
        if not _local_vision_available():
            return DesignJudgeReport(
                enabled=False, mode="disabled", provider="local-unavailable",
                average_score=0.0, reviews=[],
                summary="No local vision model is installed; L3 local judge "
                        "degraded to disabled (no VLM was called).")
        # Unreachable today: if a real local model is ever wired up, dispatch
        # here. We deliberately do not fabricate this branch.
        return DesignJudgeReport(
            enabled=False, mode="disabled", provider="local-unavailable",
            summary="Local vision model detection returned no usable provider.")

    def _report_manual(self, slides_meta: list) -> DesignJudgeReport:
        reviews: list[DesignReview] = []
        for i, meta in enumerate(slides_meta):
            sid, sidx = _slide_key(meta, i)
            reviews.append(DesignReview(
                slide_id=sid, slide_index=sidx, score=0.0, severity="info",
                visual_issues=[], suggestions=["manual visual review required"],
                dimension="overall"))
        return DesignJudgeReport(
            enabled=True, mode="manual", provider="manual-template",
            average_score=0.0, reviews=reviews,
            summary=f"Manual review template for {len(reviews)} slide(s); "
                    "scores are placeholders for a human to fill in.")

    def _report_mock(
        self,
        slides_meta: list,
        png_paths: list[str],
        validation: ValidationReport | dict | None,
        visual_findings: Iterable[VisualFinding | dict] | None,
    ) -> DesignJudgeReport:
        issues = _iter_issues(validation)
        findings = _iter_findings(visual_findings)

        # bucket issues / findings by slide index
        issues_by_slide: dict[int, list[dict[str, Any]]] = {}
        for it in issues:
            issues_by_slide.setdefault(it["slide_index"], []).append(it)
        bad_findings_by_slide: dict[int, list[dict[str, Any]]] = {}
        for f in findings:
            if not f["ok"]:
                bad_findings_by_slide.setdefault(f["slide_index"], []).append(f)

        reviews: list[DesignReview] = []
        for i, meta in enumerate(slides_meta):
            sid, sidx = _slide_key(meta, i)
            reviews.append(self._mock_review_for_slide(
                sid, sidx, _element_count(meta),
                issues_by_slide.get(sidx, []),
                bad_findings_by_slide.get(sidx, [])))

        avg = round(sum(r.score for r in reviews) / len(reviews), 2) if reviews else 0.0
        n_flagged = sum(1 for r in reviews if r.severity in ("medium", "high"))
        summary = (
            f"Heuristic L3 review of {len(reviews)} slide(s); "
            f"average design score {avg}/5; {n_flagged} slide(s) flagged. "
            "Deterministic mock reviewer — no VLM was called (advisory only).")
        return DesignJudgeReport(
            enabled=True, mode="mock", provider="mock-heuristic",
            average_score=avg, reviews=reviews, summary=summary)

    # -- the deterministic per-slide heuristic ------------------------------
    @staticmethod
    def _mock_review_for_slide(
        slide_id: str,
        slide_index: int,
        element_count: int,
        issues: list[dict[str, Any]],
        bad_findings: list[dict[str, Any]],
    ) -> DesignReview:
        """Derive a deterministic 1-5 review from issue/finding counts.

        Scoring is seedless and a pure function of its inputs:
            * each validator ERROR costs 1.5 points
            * each validator WARNING costs 0.5 points
            * each failed L2 visual finding costs 1.0 point
            * an empty slide (no elements) costs 1.0 point
        clamped to [1, 5]. Severity escalates with the worst signal present.
        """
        errors = [it for it in issues if it["severity"] == Severity.ERROR.value]
        warnings = [it for it in issues if it["severity"] == Severity.WARNING.value]
        # "info"/other issues are noted but do not move the score

        penalty = 1.5 * len(errors) + 0.5 * len(warnings) + 1.0 * len(bad_findings)
        if element_count == 0:
            penalty += 1.0

        score = max(1.0, min(5.0, 5.0 - penalty))

        # severity ladder
        if errors or element_count == 0:
            severity = "high"
        elif bad_findings:
            severity = "medium"
        elif warnings:
            severity = "low"
        else:
            severity = "info"

        # visual_issues: human-readable, deterministic order (issues then findings)
        visual_issues: list[str] = []
        suggestions: list[str] = []
        seen_suggestions: set[str] = set()

        for it in errors + warnings:
            itype = it["type"]
            msg = it["message"] or itype or "validation issue"
            label = "ERROR" if it["severity"] == Severity.ERROR.value else "WARNING"
            visual_issues.append(f"[{label}] {msg}")
            sug = _ISSUE_SUGGESTIONS.get(itype)
            if sug and sug not in seen_suggestions:
                suggestions.append(sug)
                seen_suggestions.add(sug)

        for f in bad_findings:
            note = _VISUAL_METRIC_NOTES.get(f["metric"], f"visual check '{f['metric']}' not ok")
            detail = f["detail"]
            visual_issues.append(f"[VISUAL] {note}" + (f" ({detail})" if detail else ""))
            if note not in seen_suggestions:
                suggestions.append(note)
                seen_suggestions.add(note)

        if element_count == 0 and not any("EMPTY_SLIDE" in v for v in visual_issues):
            visual_issues.append("[VISUAL] Slide appears to have no content elements.")

        if not visual_issues:
            # clean slide — positive, generic note
            visual_issues = []
            suggestions = ["Design looks clean and on-theme; no changes needed."]

        return DesignReview(
            slide_id=slide_id, slide_index=slide_index,
            score=round(score, 2), severity=severity,
            visual_issues=visual_issues, suggestions=suggestions,
            dimension="overall")


# ---------------------------------------------------------------------------
# factory
# ---------------------------------------------------------------------------
def make_design_judge(mode: str = "auto") -> VlmDesignJudgeProvider:
    """Build a design judge for the given ``mode``.

    Modes: ``disabled`` | ``mock`` | ``local`` | ``manual`` | ``auto``.
    ``auto`` resolves to ``mock`` because no external VLM/API key is present in
    this environment. See the module docstring for the honest capability note.
    """
    return VlmDesignJudgeProvider(mode=mode)


def judge_deck(
    slides_meta: list,
    png_paths: list[str],
    validation: ValidationReport | dict | None = None,
    *,
    visual_findings: Iterable[VisualFinding | dict] | None = None,
    mode: str = "auto",
) -> DesignJudgeReport:
    """Module-level convenience wrapper around :meth:`VlmDesignJudgeProvider.judge_deck`."""
    return make_design_judge(mode).judge_deck(
        slides_meta, png_paths, validation,
        visual_findings=visual_findings, mode=mode)


def _local_vision_available() -> bool:
    """Detect an *obviously* installed local vision model. Always False here.

    We do not probe the network or import heavyweight optional deps eagerly;
    we only check for the clear, deliberate presence of a local backend. None
    is installed, so this returns False and ``local`` mode degrades to disabled.
    """
    try:
        import importlib.util as _ilu

        # A local VLM backend would have to ship one of these. None are vendored.
        for name in ("vonish_local_vlm", "llama_cpp_vlm"):
            if _ilu.find_spec(name) is not None:
                return True
    except Exception:
        return False
    return False


__all__ = [
    "VlmDesignJudgeProvider",
    "make_design_judge",
    "judge_deck",
    "get_judge_modes",
]
