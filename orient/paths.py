"""Canonical filesystem paths within ORIENT_ROOT.

One place that knows the notes-tree layout, so path construction isn't re-derived
ad hoc across modules. The lib/ forks keep their own inline construction to stay
thin against upstream — these helpers are for orient's own modules.
"""
from __future__ import annotations

from pathlib import Path


def notes_root(orient_root: Path) -> Path:
    return orient_root / "notes"


def topic_dir(orient_root: Path, project: str, topic: str) -> Path:
    """Directory holding a topic's notes and per-topic artifacts: the dated
    `<date>.md` session notes plus `context.md` / `pr-context.md`."""
    return orient_root / "notes" / project / topic
