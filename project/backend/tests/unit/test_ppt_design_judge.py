"""Unit tests for the Phase-3 L3 VLM design-judge framework.

Exercises ``ppt_engine.design_judge`` — the advisory design reviewer that sits
on top of the L1 (rule) and L2 (image) gates. The L3 judge NEVER blocks
delivery; these tests pin down each mode's contract:

    * disabled — no-op, enabled False, empty reviews
    * mock     — deterministic heuristic, one review/slide, scores in [1,5]
    * mock     — flags a slide that carries a validator ERROR
    * local    — degrades gracefully to disabled (no VLM is installed)
    * manual   — per-slide template with the manual-review suggestion

Run from ``F:/Projects/VonishAgent/project/backend``::

    .venv/Scripts/python.exe -m pytest tests/unit/test_ppt_design_judge.py -q

No real VLM/MLLM is ever invoked (none exists in this environment); the mock
mode is a pure, seedless heuristic over the engine's own validation output.
"""
from __future__ import annotations

from ppt_engine.demo_decks import acceptance_deck
from ppt_engine.design_judge import (
    get_judge_modes,
    make_design_judge,
)
from ppt_engine.engine import generate_deck
from ppt_engine.schema import (
    DesignJudgeReport,
    IssueType,
    Severity,
    ValidationReport,
    ValidationSummary,
    ValidatorIssue,
)


# ---------------------------------------------------------------------------
# modes catalogue
# ---------------------------------------------------------------------------
def test_get_judge_modes():
    modes = get_judge_modes()
    assert set(modes) >= {"disabled", "mock", "local", "manual", "auto"}


# ---------------------------------------------------------------------------
# disabled
# ---------------------------------------------------------------------------
def test_disabled_mode():
    judge = make_design_judge("disabled")
    report = judge.judge_deck(
        slides_meta=[{"slide_id": "s0", "slide_index": 0, "elements": []}],
        png_paths=[],
        validation=None,
    )
    assert isinstance(report, DesignJudgeReport)
    assert report.enabled is False
    assert report.mode == "disabled"
    assert report.reviews == []


# ---------------------------------------------------------------------------
# mock — full deck, scores well-formed
# ---------------------------------------------------------------------------
def test_mock_mode_scores(tmp_path):
    result = generate_deck(acceptance_deck("tech-dark"), tmp_path, visual_qa=True)

    png_paths = [str(tmp_path / p.path) for p in result.previews]
    judge = make_design_judge("mock")
    report = judge.judge_deck(
        slides_meta=result.slides_meta,
        png_paths=png_paths,
        validation=result.validation,
        visual_findings=result.visual_findings,
    )

    assert report.enabled is True
    assert report.mode == "mock"
    assert "mock" in report.provider.lower()
    # one review per slide
    assert len(report.reviews) == len(result.slides_meta) == 12
    # every score in [1, 5]
    for r in report.reviews:
        assert 1.0 <= r.score <= 5.0, f"slide {r.slide_index} score {r.score} out of range"
        assert r.severity in {"info", "low", "medium", "high"}
    assert 1.0 <= report.average_score <= 5.0


# ---------------------------------------------------------------------------
# mock — flags a slide with a validator ERROR
# ---------------------------------------------------------------------------
def test_mock_flags_bad_slide():
    # one ERROR (text overflow) on slide 0
    bad_validation = ValidationReport(
        deck_id="bad",
        summary=ValidationSummary(total_issues=1, error_count=1),
        issues=[ValidatorIssue(
            id="iss-0", type=IssueType.TEXT_OVERFLOW, severity=Severity.ERROR,
            slide_id="s0", slide_index=0,
            message="Title text overflows its box")],
        deliverable=False, delivery_grade="blocked",
        blocking_issue_types=[IssueType.TEXT_OVERFLOW.value])

    slides_meta = [
        {"slide_id": "s0", "slide_index": 0, "elements": [{"element_id": "t"}]},
        {"slide_id": "s1", "slide_index": 1, "elements": [{"element_id": "t"}]},
    ]

    report = make_design_judge("mock").judge_deck(
        slides_meta=slides_meta, png_paths=[], validation=bad_validation)

    assert report.enabled is True and report.mode == "mock"
    review0 = next(r for r in report.reviews if r.slide_index == 0)
    assert review0.severity in {"medium", "high"}
    assert review0.visual_issues, "flagged slide must list visual issues"
    assert review0.suggestions, "flagged slide must offer suggestions"
    # the overflow penalty must drop the score below a clean slide
    assert review0.score < 5.0

    # the clean slide 1 stays positive
    review1 = next(r for r in report.reviews if r.slide_index == 1)
    assert review1.severity == "info"
    assert review1.score >= 4.0


# ---------------------------------------------------------------------------
# local — must degrade gracefully (no VLM installed), never raise
# ---------------------------------------------------------------------------
def test_local_degrades():
    judge = make_design_judge("local")
    # must NOT raise
    report = judge.judge_deck(
        slides_meta=[{"slide_id": "s0", "slide_index": 0, "elements": []}],
        png_paths=["/does/not/matter.png"],
        validation=None,
    )
    assert report.mode == "disabled"
    assert report.enabled is False
    assert "local" in report.summary.lower() or "no local" in report.summary.lower()


# ---------------------------------------------------------------------------
# manual — one template review per slide
# ---------------------------------------------------------------------------
def test_manual_template():
    slides_meta = [
        {"slide_id": "s0", "slide_index": 0, "elements": []},
        {"slide_id": "s1", "slide_index": 1, "elements": []},
        {"slide_id": "s2", "slide_index": 2, "elements": []},
    ]
    report = make_design_judge("manual").judge_deck(
        slides_meta=slides_meta, png_paths=[], validation=None)

    assert report.enabled is True
    assert report.mode == "manual"
    assert len(report.reviews) == 3
    for r in report.reviews:
        assert r.score == 0.0
        assert r.severity == "info"
        assert r.suggestions == ["manual visual review required"]


# ---------------------------------------------------------------------------
# auto — resolves to mock (no external VLM/API key present)
# ---------------------------------------------------------------------------
def test_auto_resolves_to_mock():
    judge = make_design_judge("auto")
    assert judge.mode == "mock"
    report = judge.judge_deck(
        slides_meta=[{"slide_id": "s0", "slide_index": 0, "elements": [{"element_id": "t"}]}],
        png_paths=[], validation=None)
    assert report.enabled is True
    assert report.mode == "mock"
