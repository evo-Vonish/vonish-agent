"""Unit tests for the Phase-3 rule-based Reference Deck Analyzer.

Builds a real reference ``.pptx`` with the engine itself (the 12-slide
acceptance deck), then checks that ``RuleReferenceDeckAnalyzer`` extracts a
sensible style profile, that the profile can be turned into a valid ``Theme``
which still renders a deliverable deck, and that malformed input is handled
without raising.

Run from ``F:/Projects/VonishAgent/project/backend``::

    PYTHONPATH=F:/Projects/VonishAgent/project/backend .venv/Scripts/python.exe \
        -m pytest tests/unit/test_ppt_reference.py -q
"""
from __future__ import annotations

from pathlib import Path

from ppt_engine.demo_decks import acceptance_deck
from ppt_engine.engine import generate_deck
from ppt_engine.reference_analyzer import RuleReferenceDeckAnalyzer
from ppt_engine.registry import get_layout_registry, get_theme_registry
from ppt_engine.schema import ReferenceDeckProfile, Theme


def _is_valid_hex(value: str) -> bool:
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        return False
    try:
        int(value[1:], 16)
        return True
    except ValueError:
        return False


def _make_reference_pptx(tmp_path: Path) -> str:
    """Generate the acceptance deck and return the absolute .pptx path."""
    result = generate_deck(acceptance_deck("business-bluegray"), tmp_path)
    pptx_path = tmp_path / result.pptx_path
    assert pptx_path.exists(), f"expected rendered pptx at {pptx_path}"
    return str(pptx_path)


def test_build_profile(tmp_path):
    pptx_path = _make_reference_pptx(tmp_path)
    analyzer = RuleReferenceDeckAnalyzer()
    profile = analyzer.build_profile(pptx_path)

    assert isinstance(profile, ReferenceDeckProfile)
    assert profile.slide_count == 12

    # palette: non-empty, every entry a valid #RRGGBB
    assert profile.palette, "palette should not be empty"
    assert all(_is_valid_hex(c) for c in profile.palette), profile.palette

    # fonts: non-empty
    assert profile.fonts, "fonts should not be empty"

    # element mix has text
    assert profile.element_type_counts.get("text", 0) > 0, profile.element_type_counts

    # suggested theme is a real built-in id
    theme_ids = set(get_theme_registry().list_ids())
    assert profile.suggested_theme_id in theme_ids, profile.suggested_theme_id

    # suggested layouts are all valid built-in ids, cover first
    layout_ids = set(get_layout_registry().list_ids())
    assert profile.suggested_layouts, "expected at least one suggested layout"
    assert all(lid in layout_ids for lid in profile.suggested_layouts), profile.suggested_layouts
    assert profile.suggested_layouts[0] == "cover-center"

    # analyze() returns the same data as a dict
    as_dict = analyzer.analyze(pptx_path)
    assert isinstance(as_dict, dict)
    assert as_dict["slide_count"] == 12


def test_profile_to_theme_generates(tmp_path):
    pptx_path = _make_reference_pptx(tmp_path)
    analyzer = RuleReferenceDeckAnalyzer()
    profile = analyzer.build_profile(pptx_path)

    ref_theme = analyzer.profile_to_theme(profile)
    assert isinstance(ref_theme, Theme)
    assert ref_theme.theme_id.startswith("ref-")
    # overridden tokens are valid hex
    assert _is_valid_hex(ref_theme.tokens.primary)
    assert _is_valid_hex(ref_theme.tokens.background)

    out2 = tmp_path / "gen2"
    out2.mkdir()
    result = generate_deck(acceptance_deck("tech-dark"), out2, theme=ref_theme)
    assert result.validation.deliverable is True, result.validation.delivery_grade
    assert (out2 / result.pptx_path).exists()
    assert result.theme_id == ref_theme.theme_id


def test_malformed_is_safe(tmp_path):
    analyzer = RuleReferenceDeckAnalyzer()

    # non-existent path
    p1 = analyzer.build_profile(str(tmp_path / "does_not_exist.pptx"))
    assert isinstance(p1, ReferenceDeckProfile)
    assert p1.notes

    # a non-pptx file (plain text with .pptx extension)
    bogus = tmp_path / "bogus.pptx"
    bogus.write_text("this is not a pptx", encoding="utf-8")
    p2 = analyzer.build_profile(str(bogus))
    assert isinstance(p2, ReferenceDeckProfile)
    assert p2.notes

    # analyze() on garbage also returns a dict, never raises
    d = analyzer.analyze(str(tmp_path / "nope.pptx"))
    assert isinstance(d, dict)
    assert d.get("notes")
