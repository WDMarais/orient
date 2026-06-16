"""Wraps orient.lib.preflight.route() into the public PreflightResult API."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from orient.lib.preflight import route as _route


@dataclass
class PreflightResult:
    mode: str                         # "new" | "append" | "no-prev" | "ambiguous" | "error:<detail>"
    prev_path: Optional[str] = None
    pending_count: int = 0
    deferred_count: int = 0
    append_line: Optional[int] = None
    append_pass: Optional[int] = None
    error: Optional[str] = None
    note_path: Optional[str] = None
    called_at: Optional[str] = None


def run_preflight(
    project: str,
    topic: str,
    mode: str,              # "checkpoint" | "close"
    orient_root: Path,
) -> PreflightResult:
    note_root = orient_root / "notes"
    raw = _route(project, topic, mode, note_root)

    return PreflightResult(
        mode=raw.get("mode", "error:unrecognised"),
        prev_path=raw.get("prev_path"),
        pending_count=raw.get("pending_count", 0),
        deferred_count=raw.get("deferred_count", 0),
        append_line=raw.get("append_line"),
        append_pass=raw.get("append_pass"),
        error=raw.get("error"),
        note_path=raw.get("note_path"),
        called_at=raw.get("called_at"),
    )
