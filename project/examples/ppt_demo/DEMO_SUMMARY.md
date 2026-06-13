# VonishAgent PPT Artifact Engine — E2E Demo

- **Normal theme (business-bluegray)** → `outputs/ppt/acceptance-business-bluegray/deck.pptx` · grade `perfect` · L2 findings 48 · L3 avg 5.0/5
- **Brand theme (vonish-agent)** → `outputs/ppt/acceptance-vonish-agent/deck.pptx` · grade `perfect`
- **Brand theme (vonish-ocr)** → `outputs/ppt/acceptance-vonish-ocr/deck.pptx` · grade `perfect`
- **Reference-styled** (profile from vonish-agent, suggested theme `vonish-agent`, palette 8 colours) → `outputs/ppt/reference-styled/deck.pptx` · grade `perfect`
- **Patch + rollback** on the normal deck → versions: v000/generate, v001/patch, v002/restore (patched grade `perfect`, after rollback title restored)
- **L3 design review** (mock) attached to manifest · avg 5.0/5 over 12 slides (advisory, non-blocking; not a real VLM)
- **Experimental SVG route** (NOT main chain) → direct 149 shapes / 53870 B vs SVG 162 shapes / 47513 B

## Pipeline exercised per deck
DeckDesignSpec → SlideIR → Theme/Layout Registry → PptxRenderer → L1 Validator → Auto-Repair → L2 Visual QA → (L3 Design Judge) → PNG previews → version snapshot → manifest. Patch / rollback re-run the same gate.

Open any `deck.pptx` in the Workbench: it loads `deck.manifest.json` and shows rendered PNG previews, the validation grade, clickable element selection, the issue overlay, version history (with rollback), and (when present) the L3 design review.
