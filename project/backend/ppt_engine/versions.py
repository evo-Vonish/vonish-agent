"""Deck version store — SlideIR snapshots for history & rollback.

Every generate / patch / restore writes a snapshot of the deck's SlideIR into
``<deck_dir>/versions/`` and appends an entry to ``versions/index.json``. A
restore re-renders the deck from a chosen snapshot (and itself records a new
``restore`` version, so history stays linear and auditable).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .schema import DeckVersion, SlideIR


def _versions_dir(deck_dir: Path) -> Path:
    return deck_dir / "versions"


def _index_path(deck_dir: Path) -> Path:
    return _versions_dir(deck_dir) / "index.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_versions(deck_dir: Path) -> list[DeckVersion]:
    idx = _index_path(deck_dir)
    if not idx.exists():
        return []
    try:
        raw = json.loads(idx.read_text(encoding="utf-8"))
        return [DeckVersion.model_validate(v) for v in raw]
    except Exception:
        return []


def snapshot_version(
    deck_dir: Path,
    slides: list[SlideIR],
    *,
    label: str,
    kind: str,
    grade: str = "",
) -> list[DeckVersion]:
    """Write a SlideIR snapshot, append it to the index, and return full history."""
    vdir = _versions_dir(deck_dir)
    vdir.mkdir(parents=True, exist_ok=True)
    existing = list_versions(deck_dir)
    index = len(existing)
    # stamp-free counter-based id (timestamp also recorded for display)
    version_id = f"v{index:03d}"
    snap_path = vdir / f"{version_id}.slideir.json"
    snap_path.write_text(
        json.dumps([s.model_dump(mode="json") for s in slides], ensure_ascii=False, indent=2),
        encoding="utf-8")
    entry = DeckVersion(
        version_id=version_id, index=index, label=label[:120],
        kind=kind if kind in ("generate", "patch", "restore") else "patch",
        created_at=_now_iso(), slide_count=len(slides), grade=grade,
        slideir_path=str(snap_path).replace("\\", "/"))
    history = existing + [entry]
    _index_path(deck_dir).write_text(
        json.dumps([v.model_dump(mode="json") for v in history], ensure_ascii=False, indent=2),
        encoding="utf-8")
    return history


def load_version_slides(deck_dir: Path, version_id: str) -> list[SlideIR]:
    """Load the SlideIR list from a saved snapshot."""
    for v in list_versions(deck_dir):
        if v.version_id == version_id:
            # Reconstruct from deck_dir (deterministic filename) so rollback
            # survives a relocated/copied workspace; the recorded absolute path
            # is only a fallback.
            path = deck_dir / "versions" / f"{version_id}.slideir.json"
            if not path.exists():
                recorded = Path(v.slideir_path)
                if not recorded.exists():
                    raise FileNotFoundError(f"snapshot for {version_id} is missing")
                path = recorded
            raw = json.loads(path.read_text(encoding="utf-8"))
            return [SlideIR.model_validate(d) for d in raw]
    raise KeyError(f"version {version_id} not found in {deck_dir}")
