# VonishAgent PPT Artifact Engine — Implementation Report

> **Date**: 2026-06-14 · **Status**: Phase 1 complete & verified, Phase 2 basics landed, Phase 3 interfaces reserved · **Author**: build pass per `ppt_artifact_engine_research.md`

## 1. Executive summary

The PPT Artifact Engine is implemented as a deterministic, server-side Python pipeline and wired into the agent as a first-class tool. The next time the agent makes a deck it **must** go through:

```
user request
  → DeckDesignSpec        (agent picks theme + per-slide layout + content — never pixels)
  → SlideIR               (layout engine computes every bbox / font size / colour)
  → Theme + Layout Registry (tokens own colour/typography; recipes own structure)
  → PptxRenderer          (python-pptx, native editable shapes/text/charts)
  → PptValidator          (12 rule checks: overflow, overlap, bounds, margin, small font,
                           long title, empty, overcrowded, off-theme colour, low contrast, font chaos)
  → Auto-Repair Loop      (auto-fix → re-render → re-validate, ≤3 rounds)
  → PNG previews          (Pillow renders the SAME SlideIR → preview matches the file)
  → ValidationReport + manifest written to the workspace
  → Artifact Workbench    (PptxRenderer shows PNG previews + grade badge; structural fallback)
```

**Key architectural decision:** `SlideIR` is the single source of truth. Both the `.pptx` (python-pptx) and the per-page `.png` previews (Pillow) render from the *same* IR, so the preview faithfully represents the file and the validator checks the real geometry. This also removes any LibreOffice/headless-Office dependency (none is installed).

**Verification at a glance:**
- 5 themes × 12 layouts build with **0 errors / 0 warnings → grade "perfect"** on the acceptance deck.
- Validator catches **6 distinct issue types** on a broken slide; auto-repair takes it from **"blocked" → deliverable** (overflow 40pt→8.6pt, out-of-bounds clamped, `#FF00FF`→nearest theme colour, contrast 1.32:1→17.58:1, font 8→12pt).
- **48 backend tests pass** (11 new PPT tests + existing suite, no regressions). Frontend `tsc --noEmit` and `vite build` exit 0.
- Demo decks rendered for all 5 themes (12 slides each) under `project/examples/ppt_demo/`.

## 2. What was built

### 2.1 Backend engine — `project/backend/ppt_engine/`

| File | Role |
|---|---|
| `schema.py` | Frozen data contract: `DeckDesignSpec`, `SlideSpec`, `SlideContent` (+ Card/Column/Step/Chart/Code/Quote/Diagram), `SlideIR`, `SlideElement`, `Theme`/`ThemeTokens`/`FontStack`, `LayoutRecipe`/`SlotDefinition`, `ValidatorIssue`/`ValidationReport`, `ElementPatch`/`PatchOperation`, `ArtifactPreview`, `SlideMeta`, `DeckResult`. Geometry contract: px canvas (1280×720), bbox px, fontSize pt, `1px=9525 EMU`. |
| `themes/__init__.py` | 5 themes: `tech-dark`, `academic-white`, `business-bluegray`, `vonish-agent`, `vonish-ocr` — each with full colour tokens, font stack, spacing, typography, content constraints. |
| `layouts/recipes.py` | 12 layout recipes with slots + per-layout constraints. |
| `layouts/engine.py` | The layout algorithm: recipe + content → positioned `SlideElement`s, with per-element auto-fit so text never overflows. |
| `registry.py` | `ThemeRegistry` / `LayoutRegistry` singletons + summaries for tool discovery. |
| `text_metrics.py` | Deterministic, CJK-aware text measurement (shared insets) powering overflow detection + auto-fit. |
| `renderer.py` | `PptxRenderer`: SlideIR → native `.pptx` (editable text boxes, shapes, **native charts**). |
| `preview.py` | `PillowPreviewProvider`: SlideIR → per-page PNG; `PreviewProvider` Protocol for future higher-fidelity providers. |
| `validator.py` | `PptValidator`: 12 rule checks incl. WCAG contrast + theme-conformance + content-ink crowding. |
| `autorepair.py` | `repair_loop`: validate → apply AUTO fixes → re-validate, ≤3 rounds, cumulative `auto_fixed` count. |
| `engine.py` | `generate_deck(spec, workspace_dir)` orchestrator: writes `.pptx`, PNG previews, `deck.deckspec.json`, `deck.slideir.json`, `deck.manifest.json`. |
| `builder.py` | `build_deck_spec(...)`: forgiving agent-dict → strict `DeckDesignSpec` (cards/items as `list[str]`, columns as `str`, unknown layout → fallback). |
| `interfaces.py` | **Phase 3 abstract interfaces (declared, not implemented):** `ScreenshotInspector`, `VisualReviewProvider`, `VlmDesignJudge`, `ReferenceDeckAnalyzer`, `SvgIntermediateRenderer`. Each raises `NotImplementedError`. |
| `parse.py` | **Phase 2:** `parse_pptx_to_slide_metas` / `parse_pptx_to_element_tree` — reverse path for the workbench element tree (group recursion, EMU→px). |
| `patch.py` | **Phase 2:** `apply_patch(slide_ir, ElementPatch)` (deep-copy, all 7 ops) + `apply_patch_and_rerender`. |
| `demo_decks.py` | `acceptance_deck(theme_id)` — canonical 12-slide deck covering every layout. |

### 2.2 Agent integration (existing files edited)

- `agent/tool_registry.py` — registered `generate_presentation` (full slide/content schema) + `list_presentation_options`, category `artifact`.
- `agent/tool_executor.py` — `_handle_generate_presentation` (runs the engine off-thread, returns `open_artifact:True` + previews + validation report) and `_handle_list_presentation_options`.
- `agent/agent_loop.py` — generalized the `artifact_open` SSE emission to fire for **any** tool result with `open_artifact:True` (previously only the literal `open_artifact` tool).
- `api/prompt.py` — enabled both tools in `_tool_configs`.
- `prompt/prompt_blocks.py` — behaviour rule now **requires** `generate_presentation` for decks (no hand-written python-pptx) and forbids presenting a `deliverable:false` deck as finished.

### 2.3 Frontend (existing repo, React 19 + TS)

- `frontend/src/types/ppt.ts` — TS mirror of the engine output contract (snake_case to match pydantic JSON).
- `frontend/src/components/workbench/PptxRenderer.tsx` — now a router: if a `.pptx` has a sidecar `deck.manifest.json`, renders the **high-fidelity PNG previews** with a validation **grade badge** + error/warning/auto-fixed counts and a **Rendered ↔ Structure** toggle (Structure reuses `slides_meta` for element selection + 引用). Falls back to the original structural renderer when no manifest exists. No regression to the existing path.

## 3. Wired-vs-stubbed status

| Capability | Status | Evidence |
|---|---|---|
| Theme Registry (5 themes, tokens/fonts/spacing) | ✅ wired | `themes/__init__.py`; `test_themes_have_full_tokens` |
| Layout Registry (12 recipes + algorithm) | ✅ wired | `layouts/`; `test_build_ir_all_layouts` |
| DeckDesignSpec / SlideIR / SlideElement / Theme / LayoutRecipe / ValidatorIssue / ElementPatch / ArtifactPreview / ValidationReport | ✅ wired (runtime pydantic) | `schema.py` |
| Renderer (SlideIR→PPTX, theme tokens→style, native charts) | ✅ wired | `renderer.py`; `test_renderer_opens` |
| Text overflow pre-computation + auto-fit | ✅ wired | `text_metrics.py`; `test_no_overflow_on_engine_output` |
| Validator (12 checks incl. WCAG contrast) | ✅ wired | `validator.py`; `test_validator_finds_issues` (6 types) |
| Auto-Repair Loop (≤3 rounds, no silent ship) | ✅ wired | `autorepair.py`; `test_autorepair_fixes`, `test_engine_blocks_undeliverable_is_not_silent` |
| Preview export (per-page PNG, artifact_id binding, slide/element/bbox metadata) | ✅ wired | `preview.py` + `engine.py` manifest |
| Unified agent entry (`generate_presentation`) + auto-open in Workbench | ✅ wired | `tool_executor.py`, `agent_loop.py`; live tool E2E |
| Artifact Workbench shows PPTX + PNG previews + validation grade | ✅ wired | `PptxRenderer.tsx`; `tsc`/build exit 0 |
| PPTX parse → element tree (Phase 2) | ✅ wired | `parse.py` (round-trip verified) |
| Element Patch protocol apply + re-render (Phase 2) | ✅ wired | `patch.py` |
| Element-level selection/reference on PNG overlay (Phase 2) | ◑ partial | Structure mode selects via `slides_meta`; Rendered mode is a flat image (no per-element hit-testing yet) |
| Reference-deck style learning | ⛔ stub | `interfaces.ReferenceDeckAnalyzer` (raises) |
| Screenshot inspector / OCR round-trip | ⛔ stub | `interfaces.ScreenshotInspector` (raises) |
| VLM visual review (L3) | ⛔ stub | `interfaces.VisualReviewProvider`, `VlmDesignJudge` (raise) |
| SVG → DrawingML middle layer | ⛔ stub | `interfaces.SvgIntermediateRenderer` (raises) |

Nothing in the ⛔ rows is wired into the delivery chain — by design (the brief forbids pushing unstable Phase 3 into the main pipeline).

## 4. How to use

**Agent (the required path):** call `list_presentation_options` → choose a `theme_id` + per-slide `layout`, then call `generate_presentation` with `{title, theme_id, slides:[{layout, ...content}]}`. The engine returns the artifact (auto-opens in the Workbench), per-page previews, and a validation report.

**Python API:**
```python
from ppt_engine.builder import build_deck_spec
from ppt_engine.engine import generate_deck
spec = build_deck_spec("Q2 Review", "business-bluegray", slides=[...])
result = generate_deck(spec, workspace_dir)
print(result.validation.delivery_grade, result.pptx_path)
```

**Sample artifacts** (real output of this build): `project/examples/ppt_demo/outputs/ppt/acceptance-<theme>/` — `deck.pptx`, `previews/slide-NN.png` (×12), `deck.deckspec.json` (DeckDesignSpec example), `deck.slideir.json` (SlideIR example), `deck.manifest.json` (DeckResult + validation report).

## 5. How to test
```
cd project/backend && .venv/Scripts/python.exe -m pytest tests/ -q          # 48 passed
cd project/frontend && npx tsc --noEmit && npm run build                     # exit 0
```

## 6. Risks & limitations

- **Preview fidelity:** PNG previews are rendered from SlideIR by Pillow, not by PowerPoint. They are faithful to the IR (geometry/colour/wrapping) but are not pixel-identical to PowerPoint's own renderer (e.g., font metrics differ slightly; native chart styling in the `.pptx` is richer than the preview's simplified bars). Acceptable as a proxy; a LibreOffice/headless provider can be slotted behind `PreviewProvider` later.
- **CJK in code blocks:** monospace fonts lack CJK glyphs, so the preview falls back to the CJK sans font for code containing CJK (the `.pptx` itself relies on PowerPoint per-glyph fallback). Pure-ASCII code stays monospaced.
- **Element overlap detection** is conservative (structural panels only, with containment exemption) to avoid false positives on intentional layering; hand-crafted overlaps are caught, but it is not exhaustive.
- **Phase-2 round-trip is metadata-only:** `parse.py` recovers role/type/bbox/text for the workbench overlay, not full styling/chart-data back into engine types.
- **Rendered-mode element selection** is not yet hit-testable on the PNG (Structure mode covers selection via `slides_meta`).
- **Charts** render as native column/bar/line/pie/area; pie is drawn as columns in the *preview* only.

## 7. Next steps (recommended order)

1. **Phase 2 finish:** overlay `slides_meta` element boxes on the Rendered PNG for click-to-select + Element Patch from the workbench (wire `patch.apply_patch_and_rerender` to a `patch_presentation` tool). SlideIR snapshot per edit for version rollback (fields already exist).
2. **Validator L2:** implement `ScreenshotInspector` (Laplacian blur, OCR round-trip vs SlideIR text, colour-histogram drift).
3. **Validator L3 (opt-in):** implement `VlmDesignJudge` (PPTEval 3 dimensions) gated behind a flag.
4. **More themes/layouts** (industry pack) and a chart-styling pass on the native `.pptx` charts (series colours from theme palette).
5. **Phase 3:** `SvgIntermediateRenderer` + `ReferenceDeckAnalyzer` per the research report.
