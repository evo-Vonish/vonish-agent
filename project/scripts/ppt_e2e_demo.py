"""End-to-end demo for the VonishAgent PPT Artifact Engine.

Reproducible: exercises every capability and writes the artifacts + a summary
under ``project/examples/ppt_demo/``.

    python project/scripts/ppt_e2e_demo.py

Covers: normal theme, brand themes (vonish-agent / vonish-ocr), reference-deck
style transfer, L1 validator, L2 visual QA, L3 design judge (mock), versions,
element patch, rollback, preview export, validation report, and the
experimental SVG route.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# allow running from the repo root or the scripts dir
BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from ppt_engine.demo_decks import acceptance_deck  # noqa: E402
from ppt_engine.engine import (  # noqa: E402
    apply_deck_patch,
    generate_deck,
    list_deck_versions,
    restore_deck_version,
    review_deck,
)
from ppt_engine.reference_analyzer import RuleReferenceDeckAnalyzer  # noqa: E402
from ppt_engine.svg_renderer import compare_routes  # noqa: E402
from ppt_engine.schema import SlideIR  # noqa: E402
from ppt_engine.registry import get_theme_registry  # noqa: E402

DEMO_ROOT = Path(__file__).resolve().parents[1] / "examples" / "ppt_demo"


def _title_el_id(result) -> str:
    return next(e for e in result.slides_meta[0].elements if e.role == "title").element_id


def main() -> None:
    import shutil

    ws = str(DEMO_ROOT)
    # fresh, reproducible demo: clear prior outputs so version history is clean
    shutil.rmtree(DEMO_ROOT / "outputs", ignore_errors=True)
    summary: list[str] = ["# VonishAgent PPT Artifact Engine — E2E Demo", ""]

    # 1) normal theme + L2 + L3 mock
    normal = generate_deck(acceptance_deck("business-bluegray"), ws,
                           visual_qa=True, design_judge_mode="mock")
    summary.append(f"- **Normal theme (business-bluegray)** → `{normal.pptx_path}` · "
                   f"grade `{normal.validation.delivery_grade}` · "
                   f"L2 findings {len(normal.visual_findings)} · "
                   f"L3 avg {normal.design_review.average_score:.1f}/5")

    # 2) brand themes
    for tid in ("vonish-agent", "vonish-ocr"):
        r = generate_deck(acceptance_deck(tid), ws, visual_qa=True)
        summary.append(f"- **Brand theme ({tid})** → `{r.pptx_path}` · grade `{r.validation.delivery_grade}`")

    # 3) reference-deck style transfer (use the brand deck as the reference)
    brand = generate_deck(acceptance_deck("vonish-agent"), ws, visual_qa=True)
    analyzer = RuleReferenceDeckAnalyzer()
    profile = analyzer.build_profile(str(DEMO_ROOT / brand.pptx_path))
    ref_theme = analyzer.profile_to_theme(profile, base_theme_id=profile.suggested_theme_id)
    ref_spec = acceptance_deck(profile.suggested_theme_id)
    ref_spec.deck_id = "reference-styled"
    ref_styled = generate_deck(ref_spec, ws, visual_qa=True, theme=ref_theme)
    summary.append(f"- **Reference-styled** (profile from vonish-agent, suggested theme "
                   f"`{profile.suggested_theme_id}`, palette {len(profile.palette)} colours) → "
                   f"`{ref_styled.pptx_path}` · grade `{ref_styled.validation.delivery_grade}`")

    # 4) element patch + rollback on the normal deck
    tid = _title_el_id(normal)
    patched = apply_deck_patch(ws, normal.pptx_path, 0,
                               [{"op": "replace_text", "target": tid, "value": "已被元素级 PATCH 的标题"},
                                {"op": "update_style", "target": tid, "changes": {"color": "#C9A227"}}],
                               reasoning="demo element patch", visual_qa=True)
    rolled = restore_deck_version(ws, normal.pptx_path, "v000", visual_qa=True)
    versions = list_deck_versions(ws, normal.pptx_path)
    summary.append(f"- **Patch + rollback** on the normal deck → versions: "
                   f"{', '.join(v['version_id'] + '/' + v['kind'] for v in versions)} "
                   f"(patched grade `{patched.validation.delivery_grade}`, after rollback title restored)")

    # 5) L3 review attached to manifest of the normal deck
    review = review_deck(ws, normal.pptx_path, mode="mock")
    summary.append(f"- **L3 design review** (mock) attached to manifest · avg "
                   f"{review.average_score:.1f}/5 over {len(review.reviews)} slides "
                   f"(advisory, non-blocking; not a real VLM)")

    # 6) experimental SVG route on the tech-dark acceptance deck
    td = generate_deck(acceptance_deck("tech-dark"), ws, visual_qa=True)
    raw = json.loads((DEMO_ROOT / td.slide_ir_path).read_text(encoding="utf-8"))
    slides = [SlideIR.model_validate(d) for d in raw]
    theme = get_theme_registry().get("tech-dark")
    cmp = compare_routes(slides, theme, str((DEMO_ROOT / td.pptx_path).parent / "svg"))
    summary.append(f"- **Experimental SVG route** (NOT main chain) → direct "
                   f"{cmp['direct']['shape_count']} shapes / {cmp['direct']['bytes']} B vs SVG "
                   f"{cmp['svg']['shape_count']} shapes / {cmp['svg']['bytes']} B")

    summary += [
        "",
        "## Pipeline exercised per deck",
        "DeckDesignSpec → SlideIR → Theme/Layout Registry → PptxRenderer → "
        "L1 Validator → Auto-Repair → L2 Visual QA → (L3 Design Judge) → "
        "PNG previews → version snapshot → manifest. Patch / rollback re-run the same gate.",
        "",
        "Open any `deck.pptx` in the Workbench: it loads `deck.manifest.json` and shows "
        "rendered PNG previews, the validation grade, clickable element selection, the issue "
        "overlay, version history (with rollback), and (when present) the L3 design review.",
    ]

    (DEMO_ROOT / "DEMO_SUMMARY.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary))
    print(f"\nWrote {DEMO_ROOT / 'DEMO_SUMMARY.md'}")


if __name__ == "__main__":
    main()
