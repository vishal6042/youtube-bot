"""Publishing backends. Each consumes only APPROVED drafts from the review queue."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from ..config import load_settings, resolve_path


def output_root() -> Path:
    return resolve_path(load_settings(), "output")


def find_approved(date: str | None, key: str | None, all_items: bool) -> list[tuple[Path, dict[str, Any]]]:
    """Return (metadata_path, metadata) for approved, not-yet-published items."""
    root = output_root()
    date = date or dt.date.today().isoformat()
    if key:
        paths = [root / date / key / "metadata.json"]
    else:
        paths = sorted((root / date).glob("*/metadata.json"))

    results = []
    for p in paths:
        if not p.exists():
            continue
        meta = json.loads(p.read_text(encoding="utf-8"))
        if meta.get("status") != "approved":
            continue
        results.append((p, meta))
    return results


def save_meta(path: Path, meta: dict[str, Any]) -> None:
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def read_caption(meta_path: Path) -> str:
    cap = meta_path.parent / "caption.txt"
    return cap.read_text(encoding="utf-8") if cap.exists() else ""
